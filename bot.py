import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from middlewares.admin_notify import AdminNotifyMiddleware
from handlers import start, generate, payment
from web_server import run_web_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()
    logger.info("База данных инициализирована")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.outer_middleware(AdminNotifyMiddleware())

    dp.include_router(payment.router)
    dp.include_router(start.router)
    dp.include_router(generate.router)

    logger.info("Бот запускается...")
    polling = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    )
    web = asyncio.create_task(run_web_server(bot))

    try:
        done, pending = await asyncio.wait(
            [polling, web],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    except asyncio.CancelledError:
        for task in [polling, web]:
            task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
