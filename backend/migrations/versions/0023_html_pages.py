"""Add HTML page support to notebook_pages.

Pages are markdown by default. An HTML page stores its content in
content_html and is rendered in a sandboxed iframe by the frontend, so
even AI-generated HTML with <script> tags is safe to display.

Revision ID: 0023
Revises: 0022
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE notebook_pages ADD COLUMN IF NOT EXISTS content_type "
        "VARCHAR(16) NOT NULL DEFAULT 'markdown' "
        "CHECK (content_type IN ('markdown', 'html'))"
    )
    op.execute(
        "ALTER TABLE notebook_pages ADD COLUMN IF NOT EXISTS content_html "
        "TEXT NOT NULL DEFAULT ''"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE notebook_pages DROP COLUMN IF EXISTS content_html")
    op.execute("ALTER TABLE notebook_pages DROP COLUMN IF EXISTS content_type")
