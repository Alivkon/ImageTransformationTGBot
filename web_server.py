import asyncio
import ipaddress
import logging
from functools import partial
from pathlib import Path

import aiosqlite
import yookassa
from aiohttp import web

from config import (
    TOPUP_OPTIONS,
    WEB_SERVER_PORT,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_SHOP_ID,
)
from database import add_balance, get_user, save_payment

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

YOOKASSA_IP_WHITELIST = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.154.128/25"),
    ipaddress.ip_network("2a02:5180::/32"),
    ipaddress.ip_address("77.75.156.11"),
    ipaddress.ip_address("77.75.156.35"),
]


def _is_yookassa_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for net in YOOKASSA_IP_WHITELIST:
        if isinstance(net, ipaddress.IPv4Network | ipaddress.IPv6Network):
            if addr in net:
                return True
        elif addr == net:
            return True
    return False


async def handle_pay(request: web.Request) -> web.FileResponse:
    return web.FileResponse(
        STATIC_DIR / "pay.html",
        headers={"ngrok-skip-browser-warning": "true"},
    )


async def handle_create_payment(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_id = data.get("user_id")
    amount = data.get("amount")

    if not user_id or not amount:
        return web.json_response({"error": "user_id and amount are required"}, status=400)

    try:
        user_id = int(user_id)
        amount = int(amount)
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid user_id or amount"}, status=400)

    if amount not in TOPUP_OPTIONS:
        return web.json_response({"error": f"Invalid amount. Allowed: {TOPUP_OPTIONS}"}, status=400)

    user = await get_user(user_id)
    if user is None:
        return web.json_response({"error": "User not found"}, status=404)

    loop = asyncio.get_event_loop()
    try:
        payment = await loop.run_in_executor(
            None,
            partial(
                yookassa.Payment.create,
                {
                    "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                    "confirmation": {"type": "embedded"},
                    "capture": True,
                    "description": f"Пополнение баланса на {amount}₽",
                    "metadata": {"user_id": str(user_id)},
                },
            ),
        )
    except Exception as e:
        logger.error("YooKassa create payment error: %s", e)
        return web.json_response({"error": "Payment creation failed"}, status=500)

    token = payment.confirmation.confirmation_token
    return web.json_response({"confirmation_token": token})


async def handle_webhook(request: web.Request) -> web.Response:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.remote

    if not _is_yookassa_ip(client_ip):
        logger.warning("Webhook from unknown IP: %s", client_ip)
        return web.Response(status=403)

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400)

    if data.get("type") != "notification" or data.get("event") != "payment.succeeded":
        return web.Response(status=200)

    payment_id = data.get("object", {}).get("id")
    if not payment_id:
        return web.Response(status=400)

    loop = asyncio.get_event_loop()
    try:
        payment = await loop.run_in_executor(
            None,
            partial(yookassa.Payment.find_one, payment_id),
        )
    except Exception as e:
        logger.error("YooKassa find_one error: %s", e)
        return web.Response(status=500)

    if payment.status != "succeeded":
        return web.Response(status=200)

    user_id = int(payment.metadata.get("user_id", 0))
    amount = float(payment.amount.value)

    if not user_id:
        logger.error("No user_id in payment metadata: %s", payment_id)
        return web.Response(status=200)

    try:
        await add_balance(user_id, amount)
        await save_payment(user_id=user_id, amount=amount, yookassa_payment_id=payment_id)
    except aiosqlite.IntegrityError:
        # дубль webhook — уже обработан
        return web.Response(status=200)

    bot = request.app["bot"]
    user = await get_user(user_id)
    new_balance = user["balance"] if user else amount
    try:
        await bot.send_message(
            user_id,
            f"✅ Оплата прошла успешно!\n\n"
            f"Зачислено: <b>{amount:.0f}₽</b>\n"
            f"Ваш баланс: <b>{new_balance:.0f}₽</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Failed to notify user %s: %s", user_id, e)

    return web.Response(status=200)


async def run_web_server(bot) -> None:
    yookassa.Configuration.account_id = YOOKASSA_SHOP_ID
    yookassa.Configuration.secret_key = YOOKASSA_SECRET_KEY

    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/pay", handle_pay)
    app.router.add_post("/api/payment/create", handle_create_payment)
    app.router.add_post("/yookassa/webhook", handle_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEB_SERVER_PORT)
    await site.start()
    logger.info("Web server started on port %s", WEB_SERVER_PORT)
    await asyncio.Event().wait()
