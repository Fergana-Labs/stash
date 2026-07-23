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
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Override DATABASE_URL before importing anything from the backend
_TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://stash:stash@localhost:5432/stash_test",
)
os.environ["TEST_DATABASE_URL"] = _TEST_DB_URL
os.environ["DATABASE_URL"] = _TEST_DB_URL
# Tests assume blank scopes. The default slides skill seed is
# valuable in production but breaks empty-state assertions everywhere.
# Tests that explicitly need the skill seeded call `seed_slides_skill`
# themselves.
os.environ.setdefault("STASH_DISABLE_DEFAULT_SKILL_SEEDS", "1")

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


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(_db_pool):
    """Truncate all user-data tables after each test for full isolation."""
    yield
    rows = await _db_pool.fetch(
        "SELECT format('%I.%I', schemaname, tablename) AS name "
        "FROM pg_tables "
        "WHERE schemaname = 'public' AND tablename <> 'alembic_version' "
        "ORDER BY tablename"
    )
    table_names = ", ".join(row["name"] for row in rows)
    if table_names:
        await _db_pool.execute(f"TRUNCATE {table_names} CASCADE")


def unique_name(prefix: str = "user") -> str:
    """Generate a unique username safe for use in tests."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# --- Shared cloud-agent fixture (mocks the sprite substrate seam) ---
import json as _json  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.services import sprite_agent_service, sprite_service  # noqa: E402


class FakeRedis:
    """Just enough of redis.asyncio for the per-session turn lock."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value.encode() if isinstance(value, str) else value
        return True

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        self.data.pop(key, None)


def stream_json_reply(text: str) -> list[str]:
    """A minimal well-formed claude stream-json transcript replying `text`."""
    return [
        _json.dumps({"type": "system", "subtype": "init"}),
        _json.dumps(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": text},
                },
            }
        ),
        _json.dumps({"type": "result", "subtype": "success", "result": text}),
    ]


@pytest.fixture
def sprite_exec(monkeypatch):
    """Mock the sprite seam: capture exec argv, reply via a queue of canned
    transcripts (default: echo the prompt back)."""
    calls: list[list[str]] = []
    replies: list = []

    async def fake_acquire(user_id):
        return sprite_service.Sprite(name="test-sprite")

    async def fake_exec_stream(sprite, argv, *, env, cwd=None):
        calls.append(argv)
        lines, exit_code = (
            replies.pop(0) if replies else (stream_json_reply("Reply to: " + argv[2]), 0)
        )
        for line in lines:
            yield {"stream": "stdout", "data": (line + "\n").encode()}
        yield {"exit_code": exit_code}

    # Turn-setup file writes (credential files, the MCP .mcp.json sync) go
    # through write_file, which execs on the box — capture them instead so
    # they can't consume the canned exec replies.
    writes: list[tuple[str, str]] = []

    async def fake_write_file(sprite, abs_path, contents):
        writes.append((abs_path, contents))

    monkeypatch.setattr(sprite_service, "acquire", fake_acquire)
    monkeypatch.setattr(sprite_service, "exec_stream", fake_exec_stream)
    monkeypatch.setattr(sprite_service, "write_file", fake_write_file)
    fake_redis = FakeRedis()
    monkeypatch.setattr(sprite_agent_service, "_get_redis", lambda: fake_redis)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test-key")

    class Seam:
        pass

    seam = Seam()
    seam.calls, seam.replies, seam.redis, seam.writes = calls, replies, fake_redis, writes
    return seam
