"""Show only the developer platform to new signups.

Revision ID: 0205
Revises: 0204
"""

from alembic import op

revision = "0205"
down_revision = "0204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing accounts retain both surfaces; only future accounts get the flag.
    op.execute(
        "ALTER TABLE users ADD COLUMN developer_platform_only boolean NOT NULL DEFAULT false"
    )
    op.execute("ALTER TABLE users ALTER COLUMN developer_platform_only SET DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN developer_platform_only")
