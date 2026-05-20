"""Add deleted_at + deleted_by to sessions, pages, files for soft delete.

Soft-deleted rows live in the same tables with `deleted_at` stamped. All
reads filter `deleted_at IS NULL`; the dedicated trash listing is the
only query that intentionally inverts that. No auto-purge — items stay
in trash until manually purged.

Revision ID: 0060
Revises: 0059
Create Date: 2026-05-19 00:00:00.000000
"""

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


_TABLES = ("sessions", "pages", "files")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deleted_by UUID")
        # Trash listing scans by workspace + deleted_at; partial index
        # keeps the active-row hot path unaffected.
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_trash "
            f"ON {table} (workspace_id, deleted_at DESC) "
            f"WHERE deleted_at IS NOT NULL"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_trash")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS deleted_by")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS deleted_at")
