"""Per-user pins and recently-viewed items, scoped to a workspace.

user_pins: one JSONB array of object ids per (user, workspace, kind), where
kind is 'stashes' | 'sessions' | 'files'. Mirrors the frontend's per-kind
array model so a toggle is a single upsert.

user_recents: one row per (user, workspace, object), stamped on view, read
back most-recent-first to power the Files "Recent" strip per user.

Revision ID: 0079
Revises: 0078
Create Date: 2026-05-27
"""

from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS user_pins (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind VARCHAR(16) NOT NULL,
    object_ids JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, workspace_id, kind)
)
""")
    op.execute("""
CREATE TABLE IF NOT EXISTS user_recents (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    object_id TEXT NOT NULL,
    kind VARCHAR(16) NOT NULL DEFAULT '',
    viewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, workspace_id, object_id)
)
""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_recents_recent "
        "ON user_recents(user_id, workspace_id, viewed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_recents")
    op.execute("DROP TABLE IF EXISTS user_pins")
