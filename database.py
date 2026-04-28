import aiosqlite
from datetime import datetime
from config import DB_PATH, FREE_GENERATIONS


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance REAL DEFAULT 0.0,
                free_generations INTEGER DEFAULT 1,
                total_generations INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                amount REAL NOT NULL,
                telegram_charge_id TEXT,
                provider_charge_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        try:
            await db.execute("ALTER TABLE payments ADD COLUMN username TEXT")
            await db.commit()
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE payments ADD COLUMN yookassa_payment_id TEXT")
            await db.commit()
        except Exception:
            pass
        try:
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_yookassa_id "
                "ON payments (yookassa_payment_id) WHERE yookassa_payment_id IS NOT NULL"
            )
            await db.commit()
        except Exception:
            pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                prompt TEXT,
                source_file_id TEXT,
                result_file_id TEXT,
                cost REAL DEFAULT 0.0,
                is_free INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()


async def get_or_create_user(user_id: int, username: str | None, first_name: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            await db.execute(
                "INSERT INTO users (user_id, username, first_name, free_generations) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, FREE_GENERATIONS),
            )
            await db.commit()
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()

        return dict(row)


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None


async def deduct_balance(user_id: int, amount: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (amount, user_id),
        )
        await db.commit()


async def deduct_free_generation(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET free_generations = free_generations - 1 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def increment_total_generations(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET total_generations = total_generations + 1 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def add_balance(user_id: int, amount: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await db.commit()


async def save_payment(
    user_id: int,
    amount: float,
    telegram_charge_id: str | None = None,
    provider_charge_id: str | None = None,
    username: str | None = None,
    yookassa_payment_id: str | None = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO payments
               (user_id, username, amount, telegram_charge_id, provider_charge_id, yookassa_payment_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username, amount, telegram_charge_id, provider_charge_id, yookassa_payment_id),
        )
        await db.commit()


async def create_generation(user_id: int, prompt: str, source_file_id: str, cost: float, is_free: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO generations (user_id, prompt, source_file_id, cost, is_free, status)
               VALUES (?, ?, ?, ?, ?, 'processing')""",
            (user_id, prompt, source_file_id, cost, is_free),
        )
        await db.commit()
        return cursor.lastrowid


async def complete_generation(generation_id: int, result_file_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE generations SET status = 'completed', result_file_id = ?, completed_at = ?
               WHERE id = ?""",
            (result_file_id, datetime.now().isoformat(), generation_id),
        )
        await db.commit()


async def fail_generation(generation_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE generations SET status = 'failed', completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), generation_id),
        )
        await db.commit()
