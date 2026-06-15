"""Per-comment edit tokens for the pastes pastebin.

Comments are anonymous like the pages they hang on. To let the author
edit or delete a comment later — and let agents manage comments they
post — each comment gets its own write token, minted at create time and
returned once (same model as a paste's edit_token). Deletion also
accepts the parent paste's edit_token so the page owner can moderate.

Revision ID: 0113
Revises: 0112
"""

from alembic import op

revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE paste_comments ADD COLUMN edit_token TEXT NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE paste_comments DROP COLUMN edit_token")
