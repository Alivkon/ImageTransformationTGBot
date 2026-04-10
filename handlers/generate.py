import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from config import BOT_TOKEN

logger = logging.getLogger(__name__)
from database import (
    get_user,
    get_or_create_user,
    deduct_balance,
    deduct_free_generation,
    increment_total_generations,
    create_generation,
    complete_generation,
    fail_generation,
    add_balance,
)
from services.nanobanana import generate_image, KieError
from keyboards.inline import main_menu_kb, paywall_kb
from config import GENERATION_COST, ADMIN_ID, DISCOUNTED_COST, DISCOUNTED_USER_IDS

router = Router()


@router.callback_query(F.data == "generate")
async def cb_generate(callback: CallbackQuery) -> None:
    await callback.answer()
    await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name or "",
    )
    await callback.message.answer(
        "📸 Отправьте фото с подписью — в подписи опишите желаемый результат.\n\n"
        "<b>Пример подписи:</b> «Деловой костюм, белый офисный фон, уверенная поза»\n\n"
        "<i>Лучшие результаты — при чётком изображении лица.</i>",
        parse_mode="HTML",
    )


@router.message(F.photo & F.caption)
async def got_photo_with_caption(message: Message, bot: Bot) -> None:
    user = message.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name or "")

    photo_file_id = message.photo[-1].file_id
    prompt = message.caption

    is_admin = (user.id == ADMIN_ID)
    is_discounted = (user.id in DISCOUNTED_USER_IDS)
    effective_cost = DISCOUNTED_COST if is_discounted else GENERATION_COST
    is_free = 0
    cost = float(effective_cost)

    if is_admin:
        is_free = 1
        cost = 0.0
    elif db_user["free_generations"] > 0:
        is_free = 1
        cost = 0.0
    elif db_user["balance"] < effective_cost:
        await message.answer(
            f"⚠️ Недостаточно средств.\n\n"
            f"Стоимость генерации: <b>{effective_cost}₽</b>\n"
            f"Ваш баланс: <b>{db_user['balance']:.0f}₽</b>\n\n"
            "Пополните баланс, чтобы продолжить.",
            reply_markup=paywall_kb(),
            parse_mode="HTML",
        )
        return

    processing_msg = await message.answer("⏳ Генерирую изображение, подождите...")

    generation_id = await create_generation(
        user_id=user.id,
        prompt=prompt,
        source_file_id=photo_file_id,
        cost=cost,
        is_free=is_free,
    )

    if is_free and not is_admin:
        await deduct_free_generation(user.id)
    elif not is_free:
        await deduct_balance(user.id, cost)

    await increment_total_generations(user.id)

    try:
        file = await bot.get_file(photo_file_id)
        image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        logger.info("Запрос генерации: user=%s url=%s", user.id, image_url)

        result_bytes = await generate_image(image_url, prompt)
        logger.info("Генерация завершена: user=%s размер=%d байт", user.id, len(result_bytes))

    except KieError as e:
        logger.error("KieAI ошибка: user=%s err=%s", user.id, e)
        await fail_generation(generation_id)
        if not is_free:
            await add_balance(user.id, cost)
        await processing_msg.delete()
        await message.answer(
            f"❌ Ошибка при генерации: {e}\n\nСредства возвращены на баланс.",
            reply_markup=main_menu_kb(),
        )
        return

    except Exception as e:
        logger.exception("Неожиданная ошибка при генерации: user=%s", user.id)
        await fail_generation(generation_id)
        if not is_free:
            await add_balance(user.id, cost)
        await processing_msg.delete()
        await message.answer(
            f"❌ Внутренняя ошибка: {e}\n\nСредства возвращены на баланс.",
            reply_markup=main_menu_kb(),
        )
        return

    # Отправляем результат
    try:
        result_file = BufferedInputFile(result_bytes, filename="result.jpg")
        sent = await message.answer_photo(
            result_file,
            caption="✅ Готово! Отправьте новое фото с подписью, чтобы сделать ещё одну.",
            reply_markup=main_menu_kb(),
        )
        await complete_generation(generation_id, sent.photo[-1].file_id)
        logger.info("Результат отправлен: user=%s", user.id)
    except Exception as e:
        logger.exception("Ошибка отправки результата: user=%s", user.id)
        await fail_generation(generation_id)
        await message.answer(
            f"❌ Изображение сгенерировано, но не удалось отправить: {e}",
            reply_markup=main_menu_kb(),
        )
        return

    await processing_msg.delete()


@router.message(F.photo)
async def got_photo_no_caption(message: Message) -> None:
    await message.answer(
        "📝 Добавьте подпись к фото с описанием желаемого результата и отправьте ещё раз.\n\n"
        "<b>Пример:</b> «Рыболовный костюм, осенний лес, руки в карманах»",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "balance")
async def cb_balance(callback: CallbackQuery) -> None:
    await callback.answer()
    db_user = await get_user(callback.from_user.id)
    if db_user is None:
        await callback.message.answer("Нажмите /start для начала.")
        return
    await callback.message.answer(
        f"💰 Ваш баланс: <b>{db_user['balance']:.0f}₽</b>\n"
        f"🎨 Всего генераций: <b>{db_user['total_generations']}</b>\n"
        f"🎁 Бесплатных генераций: <b>{db_user['free_generations']}</b>",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to_menu")
async def cb_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())
