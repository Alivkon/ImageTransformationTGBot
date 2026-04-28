from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from config import TOPUP_OPTIONS, WEBAPP_URL


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Сгенерировать", callback_data="generate")],
        [
            InlineKeyboardButton(text="💰 Мой баланс", callback_data="balance"),
            InlineKeyboardButton(text="➕ Пополнить", callback_data="topup"),
        ],
        [InlineKeyboardButton(text="❓ Как писать запрос", callback_data="how_to")],
    ])


def topup_amounts_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=f"{amount}₽", callback_data=f"topup_{amount}")
        for amount in TOPUP_OPTIONS
    ]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([
        InlineKeyboardButton(
            text="🌐 Оплатить через сайт",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/pay"),
        )
    ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paywall_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu")],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu")],
    ])
