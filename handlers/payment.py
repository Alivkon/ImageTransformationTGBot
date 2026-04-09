import json

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    LabeledPrice,
    PreCheckoutQuery,
)
from config import YOOKASSA_TOKEN, ADMIN_ID, MIN_TOPUP, TOPUP_OPTIONS
from database import get_user, add_balance, save_payment
from keyboards.inline import topup_amounts_kb, main_menu_kb

router = Router()


@router.message(Command("topup"))
async def cmd_topup(message: Message) -> None:
    await message.answer(
        "💳 Выберите сумму пополнения:",
        reply_markup=topup_amounts_kb(),
    )


@router.callback_query(F.data == "topup")
async def cb_topup(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "💳 Выберите сумму пополнения:",
        reply_markup=topup_amounts_kb(),
    )


@router.callback_query(F.data.startswith("topup_"))
async def cb_topup_amount(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    amount_str = callback.data.replace("topup_", "")
    try:
        amount = int(amount_str)
    except ValueError:
        await callback.message.answer("Некорректная сумма.")
        return

    if amount < MIN_TOPUP:
        await callback.message.answer(f"Минимальная сумма пополнения: {MIN_TOPUP}₽")
        return

    # Telegram Payments работает в копейках
    amount_kopecks = amount * 100

    # Чек для ЮKassa (54-ФЗ): email пользователя передаётся через send_email_to_provider
    provider_data = json.dumps({
        "receipt": {
            "items": [
                {
                    "description": f"Пополнение баланса на {amount}₽",
                    "quantity": "1.00",
                    "amount": {
                        "value": f"{amount:.2f}",
                        "currency": "RUB",
                    },
                    "vat_code": 2,          # 1 — без НДС (УСН); измените под свою систему налогообложения
                    "payment_mode": "full_payment",
                    "payment_subject": "service",
                }
            ]
        }
    })

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Пополнение баланса",
        description=(
            f"Пополнение баланса на {amount}₽ для генерации изображений.\n\n"
            "Сейчас откроется приложение для оплаты. "
            "Бот не имеет доступа к нему и не может управлять или сохранять ваши персональные данные."
        ),
        payload=f"topup_{amount}_{callback.from_user.id}",
        provider_token=YOOKASSA_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label=f"Пополнение {amount}₽", amount=amount_kopecks)],
        start_parameter="topup",
        need_email=True,
        send_email_to_provider=True,
        provider_data=provider_data,
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment = message.successful_payment
    amount_rub = payment.total_amount / 100

    payload = payment.invoice_payload
    user_id = message.from_user.id

    await add_balance(user_id, amount_rub)
    await save_payment(
        user_id=user_id,
        amount=amount_rub,
        telegram_charge_id=payment.telegram_payment_charge_id,
        provider_charge_id=payment.provider_payment_charge_id,
        username=message.from_user.username,
    )

    db_user = await get_user(user_id)
    new_balance = db_user["balance"] if db_user else amount_rub

    await message.answer(
        f"✅ Оплата прошла успешно!\n\n"
        f"Зачислено: <b>{amount_rub:.0f}₽</b>\n"
        f"Ваш баланс: <b>{new_balance:.0f}₽</b>",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )

    await message.bot.send_message(
        ADMIN_ID,
        f"💳 ОПЛАТА\n"
        f"👤 @{message.from_user.username or message.from_user.id} ({user_id})\n"
        f"💰 Сумма: {amount_rub:.0f}₽\n"
        f"🆔 Telegram charge: {payment.telegram_payment_charge_id}\n"
        f"🆔 Provider charge: {payment.provider_payment_charge_id}",
    )
