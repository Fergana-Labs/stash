"""Edit provenance for pages — who/which agent session last touched a page.

`pages.last_edit_session_id` / `last_edit_agent_name` answer the page header
question ("Edited by <agent> in session X") with no join. `page_edits` is an
append-only log so a future timeline can show more than the latest edit and so
we can trace a page back to the transcript that produced it. Human edits leave
the agent/session columns NULL.

Revision ID: 0098
Revises: 0097
"""

from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE pages
            ADD COLUMN last_edit_session_id text,
            ADD COLUMN last_edit_agent_name text
        """)
    op.execute("""
        CREATE TABLE page_edits (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            page_id      uuid NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            edited_by    uuid REFERENCES users(id),
            agent_name   text,
            session_id   text,
            op           text NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now()
        )
        """)
    op.execute("CREATE INDEX idx_page_edits_page ON page_edits (page_id, created_at DESC)")
    op.execute("CREATE INDEX idx_page_edits_session ON page_edits (workspace_id, session_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS page_edits")
    op.execute("""
        ALTER TABLE pages
            DROP COLUMN IF EXISTS last_edit_session_id,
            DROP COLUMN IF EXISTS last_edit_agent_name
        """)
