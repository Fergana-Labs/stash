"""Database pool management and schema initialisation via Alembic."""

import json
import os

import asyncpg
from pgvector.asyncpg import register_vector

from .config import settings

pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def init_db() -> None:
    global pool

    # Bootstrap pgvector extension before pool creation so that the codec
    # registration in _init_connection succeeds on every new connection.
    bootstrap = await asyncpg.connect(settings.DATABASE_URL)
    try:
        await bootstrap.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await bootstrap.close()

    # Run all pending Alembic migrations.
    # We use a thread-pool executor so that Alembic's sync SQLAlchemy code
    # doesn't block the event loop.
    import asyncio
    import functools

    def _run_alembic():
        # alembic.ini lives next to pyproject.toml at the repo root
        ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        from alembic.config import Config
        from alembic import command as alembic_cmd

        cfg = Config(ini_path)
        alembic_cmd.upgrade(cfg, "head")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, functools.partial(_run_alembic))

    pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN,
        max_size=settings.DB_POOL_MAX,
        init=_init_connection,
    )


async def close_db() -> None:
    global pool
    if pool:
        await pool.close()
        pool = None


def get_pool() -> asyncpg.Pool:
    assert pool is not None, "Database pool not initialised — call init_db() first"
    return pool
