"""Allow 'app' as an html_layout — the dashboard page-kind.

An 'app' page is full-width HTML that runs author JavaScript and binds to the
data API via window.stash. It renders only inside a sandboxed iframe with a CSP
egress-lock, so its scripts are kept (not stripped) on write.

Revision ID: 0119
Revises: 0118
"""

from alembic import op

revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_html_layout_check")
    op.execute(
        "ALTER TABLE pages ADD CONSTRAINT pages_html_layout_check "
        "CHECK (html_layout IN ('responsive', 'fixed-aspect', 'full-width', 'app'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_html_layout_check")
    op.execute(
        "ALTER TABLE pages ADD CONSTRAINT pages_html_layout_check "
        "CHECK (html_layout IN ('responsive', 'fixed-aspect', 'full-width'))"
    )
