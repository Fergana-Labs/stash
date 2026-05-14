"""Attach external Stashes to workspaces.

Revision ID: 0045
Revises: 0044
"""

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS external_stashes (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    stash_id UUID NOT NULL REFERENCES stashes(id) ON DELETE CASCADE,
    added_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, stash_id)
)
""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_stashes_stash ON external_stashes(stash_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_external_stashes_stash")
    op.execute("DROP TABLE IF EXISTS external_stashes")
