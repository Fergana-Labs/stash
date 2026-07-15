"""Workspaces: an org-owned scope with derived membership.

A workspace's knowledge base is the scope of a dedicated login-less users row
(`scope_user_id`). On-domain membership is derived: a *verified* email on
`domain` is a member, with `users.email_verified` as the trust anchor —
unverified emails must never grant membership. `workspace_members` holds only
explicit admin adds for off-domain people (contractors).

Revision ID: 0149
Revises: 0148
"""

from alembic import op

revision = "0149"
down_revision = "0148"
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
