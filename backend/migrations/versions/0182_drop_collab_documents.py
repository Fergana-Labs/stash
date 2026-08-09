"""Drop the collab editor-document tables.

The Hocuspocus collab server is removed: the editor loads and saves page
markdown directly (see PR #981), so the persisted Yjs binaries have no
reader. pages.content_markdown has always carried the exported markdown of
every edit, so no content is lost — these tables were a second copy of the
document in a format only the deleted server could read.

Revision ID: 0182
Revises: 0181
"""

from alembic import op

revision = "0182"
down_revision = "0181"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS page_collab_documents")
    op.execute("DROP TABLE IF EXISTS paste_collab_documents")


def downgrade() -> None:
    # Recreates the tables empty: the Yjs state is gone with the server, and
    # the editor bootstraps from content_markdown anyway.
    op.execute("""
CREATE TABLE IF NOT EXISTS page_collab_documents (
    page_id UUID PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
    owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    yjs_state BYTEA NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    op.execute("""
CREATE TABLE IF NOT EXISTS paste_collab_documents (
    paste_id UUID PRIMARY KEY REFERENCES pastes(id) ON DELETE CASCADE,
    yjs_state BYTEA NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
