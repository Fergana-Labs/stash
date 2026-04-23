"""Add email column to users and workspace_join_requests table.

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)")

    op.execute("""
CREATE TABLE IF NOT EXISTS workspace_join_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(8) NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'denied')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES users(id)
)
""")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS join_requests_pending_unique "
        "ON workspace_join_requests (workspace_id, user_id) "
        "WHERE status = 'pending'"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS join_requests_workspace_status "
        "ON workspace_join_requests (workspace_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_join_requests")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email")
