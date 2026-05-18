"""Add in-product Stash invitations.

Revision ID: 0057
Revises: 0056
"""

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS stash_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stash_id UUID NOT NULL REFERENCES stashes(id) ON DELETE CASCADE,
    recipient_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    invited_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission VARCHAR(16) NOT NULL DEFAULT 'read'
        CHECK(permission IN ('read', 'write', 'admin')),
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'accepted', 'dismissed')),
    target_workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at TIMESTAMPTZ,
    UNIQUE(stash_id, recipient_user_id)
)
""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stash_invites_recipient_status "
        "ON stash_invites(recipient_user_id, status, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stash_invites CASCADE")
