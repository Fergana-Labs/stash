"""Add icon_url to stashes so the detail page can show a custom logo.

The existing cover_image_url column already powers the banner. icon_url
is the small square logo shown overlapping the banner, mirroring the
workspaces.icon_url field added in 0040.

Revision ID: 0058
Revises: 0057
Create Date: 2026-05-17 00:00:00.000000
"""

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE stashes ADD COLUMN IF NOT EXISTS icon_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE stashes DROP COLUMN IF EXISTS icon_url")
