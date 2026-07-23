"""Send existing X saves back through hydration to pick up full threads.

Hydration now captures the author's whole thread plus a reply's direct
parent instead of just the conversation root, so rows hydrated under the
old renderer hold single-tweet content. Scope: the user's own Replies and
Posts — they gain the most context and, being the user's own tweets, are
rarely deleted (a vanished tweet leaves the row failed with its old content
preserved, since content only updates on success). Bookmarks are excluded:
they are other people's deletion-prone tweets, and re-archiving media mints
fresh storage keys, orphaning the old blobs.

Revision ID: 0163
Revises: 0162
"""

from alembic import op

revision = "0163"
down_revision = "0162"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE x_save_docs SET hydration_status = 'pending', hydration_attempts = 0 "
        "WHERE kind IN ('Reply', 'Post') AND hydration_status = 'done'"
    )


def downgrade() -> None:
    # Data-only nudge: rows re-hydrate on the next sync either way, and the
    # old single-tweet content is not recoverable. Nothing to restore.
    pass
