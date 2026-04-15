"""Drop auth0_sub column from users table.

Auth0 integration is removed; login is password + API key only.

Revision ID: 0006
Revises: 0001
"""
from alembic import op

revision = "0006"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auth0_sub")


def downgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth0_sub VARCHAR(128) UNIQUE")
