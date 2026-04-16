"""Alembic env for managed-only migrations.

Runs against the same Postgres instance as the OSS migrations, but tracks
its own revision chain in `alembic_version_managed` so the two don't collide.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Add project root to sys.path so we can import backend.config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from backend.config import settings  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
    "postgres://", "postgresql+asyncpg://", 1
)

_VERSION_TABLE = "alembic_version_managed"


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=_VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, version_table=_VERSION_TABLE)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_db_url, echo=False)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
