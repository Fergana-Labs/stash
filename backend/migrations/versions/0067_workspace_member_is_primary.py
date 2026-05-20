"""Mark each user's primary workspace.

The auto-provisioned workspace created at signup is the user's "primary" — the
fallback target when an agent calls /publish without a workspace_id. A partial
unique index enforces at most one primary per user.

Backfills existing users by marking their earliest membership primary so the
fallback works for accounts created before this column existed.

Revision ID: 0067
Revises: 0066
"""

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspace_members "
        "ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS workspace_members_one_primary_per_user "
        "ON workspace_members (user_id) WHERE is_primary"
    )
    op.execute(
        "UPDATE workspace_members wm SET is_primary = TRUE "
        "FROM ("
        "  SELECT DISTINCT ON (user_id) user_id, workspace_id "
        "  FROM workspace_members "
        "  ORDER BY user_id, joined_at ASC"
        ") earliest "
        "WHERE wm.user_id = earliest.user_id AND wm.workspace_id = earliest.workspace_id"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS workspace_members_one_primary_per_user")
    op.execute("ALTER TABLE workspace_members DROP COLUMN IF EXISTS is_primary")
