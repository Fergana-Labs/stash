"""Add workspace home background settings.

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-11 20:38:00.000000
"""

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

DEFAULT_HOME_BACKGROUND = (
    "jsonb_build_object("
    "'kind', 'gradient', "
    "'gradient_start', '#FED7AA', "
    "'gradient_middle', '#FEF3C7', "
    "'gradient_end', '#FFE4E6', "
    "'image_url', NULL"
    ")"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspaces "
        f"ADD COLUMN home_background JSONB NOT NULL DEFAULT {DEFAULT_HOME_BACKGROUND}"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE workspaces DROP COLUMN home_background")
