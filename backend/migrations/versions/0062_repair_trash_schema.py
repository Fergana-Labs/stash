"""Repair trash schema for databases already stamped at 0061.

Revision ID: 0062
Revises: 0061
"""

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


_TABLES = ("sessions", "pages", "files")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deleted_by UUID")
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
