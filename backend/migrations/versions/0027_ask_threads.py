"""Ask-the-stash threads + messages.

Stores the conversation history that powers the right-rail Ask agent. Each
thread is owned by (user_id, workspace_id); messages keep both the assistant
text and the tool-use trail so the UI can re-render citation chips.

Revision ID: 0027
Revises: 0026
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE ask_threads ("
        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,"
        "  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "  title TEXT NOT NULL DEFAULT '',"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX idx_ask_threads_user_workspace ON ask_threads(user_id, workspace_id, updated_at DESC)"
    )

    op.execute(
        "CREATE TABLE ask_messages ("
        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  thread_id UUID NOT NULL REFERENCES ask_threads(id) ON DELETE CASCADE,"
        "  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),"
        "  content TEXT NOT NULL DEFAULT '',"
        "  citations JSONB NOT NULL DEFAULT '[]'::jsonb,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    op.execute("CREATE INDEX idx_ask_messages_thread ON ask_messages(thread_id, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ask_messages")
    op.execute("DROP TABLE IF EXISTS ask_threads")
