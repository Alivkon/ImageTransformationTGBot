import asyncpg
from datetime import datetime
from config import DATABASE_URL, FREE_GENERATIONS

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL)
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance DOUBLE PRECISION DEFAULT 0.0,
                free_generations INTEGER DEFAULT 3,
                total_generations INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                username TEXT,
                amount DOUBLE PRECISION NOT NULL,
                telegram_charge_id TEXT,
                provider_charge_id TEXT,
                yookassa_payment_id TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_yookassa_id
            ON payments (yookassa_payment_id)
            WHERE yookassa_payment_id IS NOT NULL
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                prompt TEXT,
                source_file_id TEXT,
                result_file_id TEXT,
                cost DOUBLE PRECISION DEFAULT 0.0,
                is_free INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                completed_at TIMESTAMPTZ
            )
        """)


async def get_or_create_user(user_id: int, username: str | None, first_name: str) -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if row is None:
            await conn.execute(
                "INSERT INTO users (user_id, username, first_name, free_generations) VALUES ($1, $2, $3, $4)",
                user_id, username, first_name, FREE_GENERATIONS,
            )
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row)


async def get_user(user_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None


async def deduct_balance(user_id: int, amount: float) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
            amount, user_id,
        )


async def deduct_free_generation(user_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET free_generations = free_generations - 1 WHERE user_id = $1",
            user_id,
        )


async def increment_total_generations(user_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET total_generations = total_generations + 1 WHERE user_id = $1",
            user_id,
        )


async def add_balance(user_id: int, amount: float) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
            amount, user_id,
        )


async def save_payment(
    user_id: int,
    amount: float,
    telegram_charge_id: str | None = None,
    provider_charge_id: str | None = None,
    username: str | None = None,
    yookassa_payment_id: str | None = None,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO payments
               (user_id, username, amount, telegram_charge_id, provider_charge_id, yookassa_payment_id)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            user_id, username, amount, telegram_charge_id, provider_charge_id, yookassa_payment_id,
        )


async def create_generation(user_id: int, prompt: str, source_file_id: str, cost: float, is_free: int) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO generations (user_id, prompt, source_file_id, cost, is_free, status)
               VALUES ($1, $2, $3, $4, $5, 'processing')
               RETURNING id""",
            user_id, prompt, source_file_id, cost, is_free,
        )
        return row["id"]


async def complete_generation(generation_id: int, result_file_id: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """UPDATE generations SET status = 'completed', result_file_id = $1, completed_at = $2
               WHERE id = $3""",
            result_file_id, datetime.now(), generation_id,
        )


async def fail_generation(generation_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE generations SET status = 'failed', completed_at = $1 WHERE id = $2",
            datetime.now(), generation_id,
        )


async def get_admin_users(limit: int = 200, offset: int = 0) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT user_id, username, first_name, balance,
                   free_generations, total_generations, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """, limit, offset)
        return [dict(r) for r in rows]


async def set_free_generations(user_id: int, count: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET free_generations = $1 WHERE user_id = $2",
            count, user_id,
        )


async def get_admin_stats() -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM users) AS total_users,
                (SELECT COUNT(*) FROM generations) AS total_generations,
                (SELECT COUNT(*) FROM generations WHERE status = 'completed') AS completed_generations,
                (SELECT COUNT(*) FROM generations WHERE status = 'failed') AS failed_generations,
                (SELECT COALESCE(SUM(amount), 0) FROM payments) AS total_revenue
        """)
        return dict(row)


async def get_admin_generations(limit: int = 50, offset: int = 0) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT g.id, g.user_id, u.username, u.first_name,
                   g.prompt, g.status, g.cost, g.is_free,
                   g.created_at, g.completed_at
            FROM generations g
            JOIN users u ON u.user_id = g.user_id
            ORDER BY g.created_at DESC
            LIMIT $1 OFFSET $2
        """, limit, offset)
        return [dict(r) for r in rows]


async def get_admin_payments(limit: int = 50, offset: int = 0) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.id, p.user_id, u.username, u.first_name,
                   p.amount, p.yookassa_payment_id,
                   p.telegram_charge_id, p.created_at
            FROM payments p
            JOIN users u ON u.user_id = p.user_id
            ORDER BY p.created_at DESC
            LIMIT $1 OFFSET $2
        """, limit, offset)
        return [dict(r) for r in rows]
