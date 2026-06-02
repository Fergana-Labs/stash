"""Session folders — a shareable grouping for sessions (like file folders).

Sessions can be organized into folders; sharing a session folder (via the `shares`
table) cascades to the sessions inside it, exactly like file folders cascade to
their pages/files.

Revision ID: 0083
Revises: 0082
"""

from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE session_folders (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name          text NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),
            updated_at    timestamptz NOT NULL DEFAULT now()
        )
        """)
    op.execute(
        "ALTER TABLE sessions ADD COLUMN session_folder_id uuid "
        "REFERENCES session_folders(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX session_folders_owner_idx ON session_folders (workspace_id, owner_user_id)"
    )
    op.execute("CREATE INDEX sessions_session_folder_idx ON sessions (session_folder_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sessions_session_folder_idx")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS session_folder_id")
    op.execute("DROP TABLE IF EXISTS session_folders")
