"""Allow user-set session titles that survive auto-regeneration.

Revision ID: 0078
Revises: 0077
"""

from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE session_titles "
        "ADD COLUMN IF NOT EXISTS user_set BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE session_titles DROP COLUMN IF EXISTS user_set")
