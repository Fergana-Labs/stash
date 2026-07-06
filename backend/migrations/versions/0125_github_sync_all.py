"""GitHub all-repos mode: user_integrations.sync_all.

When set on a github connection, every repo the account can see gets a
github_repo source, and the hourly reconcile picks up repos the user gains
access to later.

Revision ID: 0125
Revises: 0124
"""

from alembic import op

revision = "0125"
down_revision = "0124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_integrations ADD COLUMN sync_all boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE user_integrations DROP COLUMN sync_all")
