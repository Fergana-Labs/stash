"""Add icon_url and color_gradient to workspaces for the new settings page.

Banner uploads already use the existing cover_image_url column. These two
add a separate icon/logo and a custom color gradient for the workspace
hero area.

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-13 00:00:01.000000
"""

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS icon_url TEXT")
    op.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS color_gradient TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS color_gradient")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS icon_url")
