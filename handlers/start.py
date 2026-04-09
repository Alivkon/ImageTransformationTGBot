from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from database import get_or_create_user
from keyboards.inline import main_menu_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    db_user = await get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name or "",
    )
    free = db_user["free_generations"]
    balance = db_user["balance"]

    free_text = f"У вас есть <b>1 бесплатная генерация</b>!" if free > 0 else ""

    await message.answer(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я помогу изменить ваше фото: оставлю ваше лицо, но изменю позу, одежду или фон "
        "по вашему описанию.\n\n"
        f"{free_text}\n"
        f"💰 Баланс: <b>{balance:.0f}₽</b>\n\n"
        "Нажмите <b>«Сгенерировать»</b>, чтобы начать.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
