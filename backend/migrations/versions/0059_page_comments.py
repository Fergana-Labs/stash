"""Add page comment threads + messages for inline anchored comments.

Threads carry the anchor metadata (quoted_text + 32-char prefix/suffix)
so a comment whose inline `<span data-comment-id>` wrapper gets deleted
or clobbered can still be surfaced in the sidebar by its quoted text.

Revision ID: 0059
Revises: 0058
Create Date: 2026-05-18 00:00:00.000000
"""

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS page_comment_threads (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          page_id       UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
          quoted_text   TEXT NOT NULL,
          prefix        TEXT NOT NULL DEFAULT '',
          suffix        TEXT NOT NULL DEFAULT '',
          created_by    UUID NOT NULL REFERENCES users(id),
          created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          resolved_at   TIMESTAMPTZ,
          resolved_by   UUID REFERENCES users(id),
          orphaned      BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_page_comment_threads_page_id "
        "ON page_comment_threads(page_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS page_comment_messages (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          thread_id   UUID NOT NULL REFERENCES page_comment_threads(id) ON DELETE CASCADE,
          author_id   UUID NOT NULL REFERENCES users(id),
          body        TEXT NOT NULL,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          edited_at   TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_page_comment_messages_thread_id "
        "ON page_comment_messages(thread_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS page_comment_messages")
    op.execute("DROP TABLE IF EXISTS page_comment_threads")
