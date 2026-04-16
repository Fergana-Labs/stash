"""Add workspace_invite_tokens table for magic-link invites.

Unlike workspaces.invite_code (a forever-secret anyone can redeem repeatedly),
these tokens are single-use-or-capped, TTL-bounded, revocable, and hashed at
rest. Used by `stash invite` + `stash connect --invite`.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS workspace_invite_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    max_uses INT NOT NULL DEFAULT 1,
    uses_count INT NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
)
""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_invite_tokens_workspace "
        "ON workspace_invite_tokens(workspace_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_invite_tokens CASCADE")
