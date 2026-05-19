"""Require user display names.

Revision ID: 0060
Revises: 0059
"""

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET display_name = name "
        "WHERE display_name IS NULL OR btrim(display_name) = ''"
    )
    op.execute("ALTER TABLE users ALTER COLUMN display_name SET NOT NULL")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_display_name_not_empty")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_display_name_not_empty "
        "CHECK (btrim(display_name) <> '')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_display_name_not_empty")
    op.execute("ALTER TABLE users ALTER COLUMN display_name DROP NOT NULL")
