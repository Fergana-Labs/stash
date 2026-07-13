"""Workspaces: an org-owned scope with stored membership.

A workspace's knowledge base is the scope of a dedicated login-less users row
(`scope_user_id`). Membership is the single source of truth the permission
predicate reads; rows arrive via domain auto-enroll (verified email domain
matches `domain`) or an explicit admin add. `users.email_verified` is the
trust anchor for auto-enroll — unverified emails must never grant membership.

Revision ID: 0144
Revises: 0143
"""

from alembic import op

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspaces (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            domain TEXT NOT NULL UNIQUE
                CHECK (domain = lower(domain) AND domain NOT LIKE '%@%'),
            scope_user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE workspace_members (
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX workspace_members_user_idx ON workspace_members (user_id)")
    op.execute("ALTER TABLE users ADD COLUMN email_verified boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN email_verified")
    op.execute("DROP TABLE workspace_members")
    op.execute("DROP TABLE workspaces")
