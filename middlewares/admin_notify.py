from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, Update
from config import ADMIN_ID
from database import get_user


class AdminNotifyMiddleware(BaseMiddleware):
    """
    Outer middleware — после каждого обработанного update дублирует
    краткое описание действия администратору.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)

        bot = data.get("bot")
        if bot is None:
            return result

        try:
            await self._notify(bot, event)
        except Exception:
            pass

        return result

    async def _notify(self, bot, event: TelegramObject) -> None:
        update: Update | None = None
        if isinstance(event, Update):
            update = event

        if update is None:
            return

        user = None
        action = ""

        if update.message and update.message.from_user:
            tg_user = update.message.from_user
            if tg_user.id == ADMIN_ID:
                return
            user_data = await get_user(tg_user.id)
            user = tg_user

            msg = update.message
            if msg.photo:
                action = "отправил фото для генерации"
            elif msg.text and msg.text.startswith("/start"):
                action = "запустил бота (/start)"
            elif msg.text and msg.text.startswith("/topup"):
                action = "запросил пополнение (/topup)"
            elif msg.successful_payment:
                payment = msg.successful_payment
                amount = payment.total_amount / 100
                action = f"оплатил {amount:.0f}₽ (charge: {payment.telegram_payment_charge_id})"
            elif msg.text:
                preview = msg.text[:60] + ("…" if len(msg.text) > 60 else "")
                action = f"написал: «{preview}»"
            else:
                action = "прислал сообщение"

        elif update.callback_query and update.callback_query.from_user:
            tg_user = update.callback_query.from_user
            if tg_user.id == ADMIN_ID:
                return
            user_data = await get_user(tg_user.id)
            user = tg_user
            cb_data = update.callback_query.data or ""
            if cb_data.startswith("topup_"):
                amount = cb_data.replace("topup_", "")
                action = f"выбрал пополнение на {amount}₽"
            elif cb_data == "topup":
                action = "открыл меню пополнения"
            elif cb_data == "balance":
                action = "запросил баланс"
            elif cb_data == "generate":
                action = "нажал «Сгенерировать»"
            elif cb_data == "back_to_menu":
                action = "вернулся в меню"
            else:
                action = f"нажал кнопку: {cb_data}"
        else:
            return

        if user is None:
            return

        name = user.first_name or ""
        username_str = f"@{user.username}" if user.username else f"id:{user.id}"
        balance_str = f"{user_data['balance']:.0f}₽" if user_data else "—"
        gens_str = str(user_data["total_generations"]) if user_data else "—"
        free_str = str(user_data["free_generations"]) if user_data else "—"

        text = (
            f"👤 {name} {username_str} ({user.id})\n"
            f"📝 Действие: {action}\n"
            f"💰 Баланс: {balance_str} | Генераций: {gens_str} | Бесплатных: {free_str}"
        )
        await bot.send_message(ADMIN_ID, text)

        # Копируем само сообщение (фото, текст и т.д.) в чат админа
        if update.message and update.message.from_user:
            msg = update.message
            if msg.photo or msg.text:
                await bot.copy_message(
                    chat_id=ADMIN_ID,
                    from_chat_id=msg.chat.id,
                    message_id=msg.message_id,
                )
