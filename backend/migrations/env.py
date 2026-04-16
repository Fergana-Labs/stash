import asyncio
import os
import sys
from logging.config import fileConfig
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Add project root to sys.path so we can import backend.config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.config import settings  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Build asyncpg URL from DATABASE_URL (handles both postgres:// and postgresql:// schemes).
_db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
    "postgres://", "postgresql+asyncpg://", 1
)

# asyncpg doesn't accept libpq-style query params (sslmode, channel_binding) that managed
# Postgres providers like Neon include by default. Strip them and translate sslmode into
# an explicit ssl connect arg.
_parsed = urlparse(_db_url)
_query = dict(parse_qsl(_parsed.query))
_ssl_required = _query.pop("sslmode", None) in ("require", "verify-ca", "verify-full")
_query.pop("channel_binding", None)
_db_url = urlunparse(_parsed._replace(query=urlencode(_query)))
_connect_args = {"ssl": "require"} if _ssl_required else {}


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL output)."""
    context.configure(
        url=_db_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_db_url, echo=False, connect_args=_connect_args)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
