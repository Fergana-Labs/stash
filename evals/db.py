"""Async database bootstrap for the eval harness.

Mirrors backend/tests/conftest.py but as a standalone async context manager
so the harness can run without pytest.
"""

from __future__ import annotations

import asyncio
import functools
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import asyncpg
from pgvector.asyncpg import register_vector

from evals.config import cfg

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"

_TRUNCATE_TABLES = [
    "webhook_deliveries", "webhooks",
    "documents", "files",
    "object_shares", "object_permissions",
    "sleep_watermarks", "sleep_configs", "injection_sessions", "injection_configs",
    "history_events",
    "page_relations",
    "page_links", "notebook_pages", "notebook_folders",
    "deck_share_page_views", "deck_share_views", "deck_shares",
    "table_rows",
    "chat_watches", "chat_messages",
    "workspace_members",
    "chats", "notebooks", "histories", "decks", "tables",
    "workspaces", "users",
]


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


def _run_alembic(db_url: str) -> None:
    from alembic import command as alembic_cmd
    from alembic.config import Config

    alembic_cfg = Config(str(_ALEMBIC_INI))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cmd.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def eval_db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """Bootstrap the test database and yield an asyncpg pool.

    Usage::

        async with eval_db_pool() as pool:
            # pool is ready; backend db_module.pool is also set
            ...
    """
    db_url = cfg.test_db_url
    os.environ["DATABASE_URL"] = db_url

    conn = await asyncpg.connect(db_url)
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    await conn.close()

    # Alembic migrations (idempotent)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, functools.partial(_run_alembic, db_url))

    pool = await asyncpg.create_pool(
        db_url, min_size=2, max_size=5, init=_init_connection
    )

    # Wire into backend database module so service calls work
    try:
        from backend import database as db_module  # noqa: PLC0415

        db_module.pool = pool
    except ImportError:
        pass

    try:
        yield pool
    finally:
        try:
            from backend import database as db_module  # noqa: PLC0415

            db_module.pool = None
        except ImportError:
            pass
        await pool.close()


async def truncate_all(pool: asyncpg.Pool) -> None:
    """Wipe all eval data between scenarios."""
    for table in _TRUNCATE_TABLES:
        try:
            await pool.execute(f"TRUNCATE {table} CASCADE")
        except Exception:
            pass
