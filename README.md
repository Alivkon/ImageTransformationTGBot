# ImageTransformationTGBot — Telegram-бот для AI-генерации фото

Коммерческий Telegram-бот, позволяющий пользователям трансформировать свои фотографии с помощью нейросети: сохраняет лицо, но меняет позу, одежду или фон по текстовому описанию.

---

## Стек технологий

| Область | Инструменты |
|---|---|
| Язык | Python 3.11+ |
| Telegram-фреймворк | aiogram 3.13 (async) |
| БД | PostgreSQL 16 + asyncpg |
| HTTP / Web | aiohttp 3.10 |
| Оплата | ЮKassa (Telegram Payments + WebApp) |
| AI-генерация | KIE.ai REST API |
| Конфигурация | python-dotenv |
| Деплой | Docker Compose + Traefik (TLS) |

---

## Ключевые возможности

- **AI-трансформация фото** — пользователь отправляет фото с текстовым промптом, бот возвращает перегенерированное изображение
- **Платёжная система** — ЮKassa через Telegram Payments и встроенный WebApp (`/pay`)
- **Баланс и монетизация** — внутренний кошелёк, пополнение на суммы 100 / 500 / 1000 / 2000 ₽
- **Бесплатные генерации** — настраиваемое количество для новых пользователей
- **Скидочные пользователи** — список ID с пониженной ценой генерации
- **Надёжная обработка ошибок** — при сбое генерации средства автоматически возвращаются на баланс
- **Админ-уведомления** — middleware дублирует администратору каждое действие пользователя (фото-запрос и результат генерации)
- **Admin WebApp** — защищённая панель (`/admin`) с просмотром статистики, генераций, платежей и управлением пользователями

---

## Архитектура

```
ImageTransformationTGBot/
├── bot.py              # Точка входа, инициализация Dispatcher и веб-сервера
├── config.py           # Конфигурация через env-переменные
├── database.py         # Слой данных (PostgreSQL, async CRUD)
├── web_server.py       # aiohttp-сервер: платёжный WebApp, ЮKassa webhook, admin API
├── handlers/
│   ├── start.py        # /start, регистрация пользователя
│   ├── generate.py     # Приём фото, запуск генерации, отправка результата
│   └── payment.py      # Пополнение баланса, обработка успешных платежей
├── services/
│   └── nanobanana.py   # Клиент KIE.ai API (создание задачи + polling статуса)
├── keyboards/
│   └── inline.py       # Inline-клавиатуры (включая кнопку Admin WebApp для ADMIN_ID)
├── middlewares/
│   └── admin_notify.py # Middleware уведомлений администратора
└── static/
    ├── pay.html         # WebApp страница оплаты ЮKassa
    └── admin.html       # Admin WebApp: статистика, генерации, платежи, пользователи
```

---

## Технические решения

### Асинхронная архитектура
Весь стек построен на `asyncio`: aiogram, asyncpg, aiohttp — без блокирующих вызовов.

### Polling внешнего API
Генерация изображений занимает несколько секунд. Реализован неблокирующий polling с таймаутом.

### Атомарность операций с балансом
Списание средств происходит до запроса к API. При любой ошибке баланс восстанавливается — пользователь не теряет деньги.

### Admin WebApp с аутентификацией
Панель администратора открывается через Telegram WebApp (кнопка видна только `ADMIN_ID`). Все API-запросы валидируются через HMAC-SHA256 проверку Telegram `initData` — без паролей и токенов в URL.

### Защита от дублирования платежей
Уникальный индекс по `yookassa_payment_id` гарантирует идемпотентность обработки webhook.

---

## База данных

Три таблицы: `users`, `payments`, `generations`.

| Таблица | Ключевые поля |
|---|---|
| `users` | `user_id`, `balance`, `free_generations`, `total_generations` |
| `payments` | `user_id`, `amount`, `yookassa_payment_id`, `telegram_charge_id` |
| `generations` | `user_id`, `prompt`, `status`, `cost`, `is_free`, `created_at`, `completed_at` |

---

## Запуск

### Docker Compose (рекомендуется)

```bash
# 1. Заполнить .env (см. раздел «Переменные окружения»)
cp .env.example .env

# 2. Собрать образ и запустить
docker compose build --no-cache
docker compose up -d

# Логи
docker compose logs -f bot
```

Проект рассчитан на работу в сети `n8n_default` с Traefik в качестве reverse proxy (TLS через Let's Encrypt).

### Локально

```bash
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

---

## Переменные окружения

| Переменная | Описание | Обязательная |
|---|---|---|
| `BOT_TOKEN` | Токен бота от @BotFather | ✓ |
| `KIE_API_KEY` | API-ключ KIE.ai | ✓ |
| `ADMIN_ID` | Telegram ID администратора | ✓ |
| `DATABASE_URL` | PostgreSQL DSN (`postgresql://user:pass@host/db`) | ✓ |
| `YOOKASSA_SHOP_ID` | ID магазина ЮKassa | ✓ |
| `YOOKASSA_SECRET_KEY` | Секретный ключ ЮKassa | ✓ |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL (для docker-compose) | ✓ |
| `YOOKASSA_TOKEN` | Токен провайдера (Telegram Payments) | ✓ |
| `WEBAPP_URL` | Публичный URL бота (напр. `https://imagetransformation.ru`) | ✓ |
| `GENERATION_COST` | Стоимость генерации в ₽ (по умолчанию `20`) | |
| `DISCOUNTED_COST` | Стоимость для скидочных пользователей (по умолчанию `5`) | |
| `DISCOUNTED_USER_IDS` | Comma-separated список Telegram ID со скидкой | |
| `MIN_TOPUP` | Минимальная сумма пополнения (по умолчанию `100`) | |
| `FREE_GENERATIONS` | Бесплатных генераций для новых пользователей (по умолчанию `1`) | |
| `WEB_SERVER_PORT` | Порт aiohttp-сервера (по умолчанию `8080`) | |
