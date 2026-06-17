"""Allow 'full-width' as an html_layout.

Adds a third layout mode to the pages.html_layout CHECK constraint. Like
'responsive' the iframe auto-sizes its height, but the parent drops the
1200px reading-column cap so the page uses the full window width (keeping the
comment rail). Right for web-page-style HTML that wants real responsive room.

Revision ID: 0117
Revises: 0116
"""

from alembic import op

revision = "0117"
down_revision = "0116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_html_layout_check")
    op.execute(
        "ALTER TABLE pages ADD CONSTRAINT pages_html_layout_check "
        "CHECK (html_layout IN ('responsive', 'fixed-aspect', 'full-width'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_html_layout_check")
    op.execute(
        "ALTER TABLE pages ADD CONSTRAINT pages_html_layout_check "
        "CHECK (html_layout IN ('responsive', 'fixed-aspect'))"
    )
