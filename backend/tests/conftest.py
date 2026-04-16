"""Shared pytest fixtures for backend tests.

A fresh Postgres database is created for the entire test session, Alembic
migrations are applied once, and a FastAPI AsyncClient is yielded to each test.

Each test's side-effects are cleaned up via TRUNCATE on teardown, keeping
tests fully isolated without needing to recreate the schema between them.

Required env vars (defaults work against the Docker Compose postgres):
    TEST_DATABASE_URL  e.g. postgresql://stash:stash@localhost:5432/stash_test
"""

import asyncio
import os
import uuid

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Override DATABASE_URL before importing anything from the backend
_TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://stash:stash@localhost:5432/stash_test",
)
os.environ["DATABASE_URL"] = _TEST_DB_URL

from backend import database as db_module  # noqa: E402
from backend.main import app  # noqa: E402 — must come after env override


@pytest_asyncio.fixture(scope="session")
async def _db_pool():
    """Bootstrap the test database once per session."""
    # Ensure pgvector is available
    conn = await asyncpg.connect(_TEST_DB_URL)
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await conn.close()

    # Run Alembic migrations against the test DB
    import functools

    def _run_alembic():
        ini_path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
        from alembic import command as alembic_cmd
        from alembic.config import Config

        cfg = Config(ini_path)
        alembic_cmd.upgrade(cfg, "head")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, functools.partial(_run_alembic))

    # Create the shared pool used by the app
    import json

    from pgvector.asyncpg import register_vector

    async def _init_connection(conn):
        await register_vector(conn)
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )
        await conn.set_type_codec(
            "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    pool = await asyncpg.create_pool(_TEST_DB_URL, min_size=2, max_size=5, init=_init_connection)
    db_module.pool = pool
    yield pool
    await pool.close()
    db_module.pool = None


@pytest_asyncio.fixture
async def client(_db_pool):
    """An httpx AsyncClient wired to the FastAPI app.

    Does NOT use the full lifespan (avoids LISTEN/NOTIFY and background tasks
    in tests).  The pool is set directly on db_module above.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def pool(_db_pool):
    """Direct asyncpg pool access for low-level assertions."""
    yield _db_pool


_TRUNCATE_TABLES = [
    "webhook_deliveries",
    "webhooks",
    "documents",
    "files",
    "object_shares",
    "object_permissions",
    "history_events",
    "session_transcripts",
    "page_links",
    "notebook_pages",
    "notebook_folders",
    "deck_share_page_views",
    "deck_share_views",
    "deck_shares",
    "table_rows",
    "chat_messages",
    "workspace_members",
    "chats",
    "notebooks",
    "histories",
    "decks",
    "tables",
    "workspaces",
    "users",
]


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(_db_pool):
    """Truncate all user-data tables after each test for full isolation."""
    yield
    for table in _TRUNCATE_TABLES:
        try:
            await _db_pool.execute(f"TRUNCATE {table} CASCADE")
        except Exception:
            pass


def unique_name(prefix: str = "user") -> str:
    """Generate a unique username safe for use in tests."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"
