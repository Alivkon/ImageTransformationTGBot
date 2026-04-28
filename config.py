import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
KIE_API_KEY: str = os.environ["KIE_API_KEY"]
YOOKASSA_TOKEN: str = os.environ["YOOKASSA_TOKEN"]
ADMIN_ID: int = int(os.environ["ADMIN_ID"])

GENERATION_COST: int = int(os.getenv("GENERATION_COST", "20"))
DISCOUNTED_COST: int = int(os.getenv("DISCOUNTED_COST", "5"))
DISCOUNTED_USER_IDS: set[int] = {
    int(x) for x in os.getenv("DISCOUNTED_USER_IDS", "").split(",") if x.strip()
}
MIN_TOPUP: int = int(os.getenv("MIN_TOPUP", "100"))
DB_PATH: str = os.getenv("DB_PATH", "bot.db")
FREE_GENERATIONS: int = int(os.getenv("FREE_GENERATIONS", "1"))

TOPUP_OPTIONS = [100, 500, 1000, 2000]

YOOKASSA_SHOP_ID: str = os.environ["YOOKASSA_SHOP_ID"]
YOOKASSA_SECRET_KEY: str = os.environ["YOOKASSA_SECRET_KEY"]
WEBAPP_URL: str = os.getenv("WEBAPP_URL", "https://imagetransformation.ru")
WEB_SERVER_PORT: int = int(os.getenv("WEB_SERVER_PORT", "8080"))
