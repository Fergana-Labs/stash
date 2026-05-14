"""Add html_layout column to pages.

HTML pages render inside a sandboxed iframe. The iframe has no idea how tall
its content "wants" to be, so the parent has to decide the box. Two modes:

- 'responsive' (default): inject a tiny ResizeObserver+postMessage bootstrap
  into the rendered HTML so the page reports its natural height back to the
  parent, which then sizes the iframe to fit. Right for documents, cards,
  dashboards — content where the height is a property of the content.

- 'fixed-aspect': lock the iframe to a 16:9 box. Right for slides / decks
  where the canvas is intentional and growing it would break the design.

Both modes share the same sandbox; only the parent's sizing strategy differs.

Revision ID: 0041
Revises: 0040
"""

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE pages ADD COLUMN IF NOT EXISTS html_layout "
        "VARCHAR(16) NOT NULL DEFAULT 'responsive' "
        "CHECK (html_layout IN ('responsive', 'fixed-aspect'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pages DROP COLUMN IF EXISTS html_layout")
