"""Threaded replies for paste comments.

A reply is a comment with ``parent_id`` set to the comment it answers.
Top-level comments carry the page anchor (quoted_text/prefix/suffix);
replies hang off them and inherit that context. Deleting a comment
cascades to its replies.

Revision ID: 0114
Revises: 0113
"""

from alembic import op

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE paste_comments ADD COLUMN IF NOT EXISTS parent_id UUID "
        "REFERENCES paste_comments(id) ON DELETE CASCADE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE paste_comments DROP COLUMN parent_id")
