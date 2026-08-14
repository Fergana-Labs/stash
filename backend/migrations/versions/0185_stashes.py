"""Multiple stashes per user.

A stash is an isolated content scope — its own files, sessions, memory, and
integrations. Like a workspace, a stash's scope is a dedicated login-less
`users` row, so every `owner_user_id`-keyed table isolates it for free. Unlike
a workspace, membership is ownership: the human in `owner_user_id` owns the
scope outright. A user's first stash is their own `users` row and has no row
here.

Revision ID: 0185
Revises: 0184
"""

from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE stashes (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name          TEXT NOT NULL,
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            scope_user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_stashes_owner ON stashes (owner_user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE stashes")
