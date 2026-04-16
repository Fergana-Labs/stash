"""Add auth0_sub column to users (managed-only).

Revision ID: m0001
Revises:
"""

from alembic import op

revision = "m0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth0_sub VARCHAR(128) UNIQUE")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_auth0_sub ON users(auth0_sub) WHERE auth0_sub IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_auth0_sub")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auth0_sub")
