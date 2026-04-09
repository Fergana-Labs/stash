"""Add auth0_sub to users table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-07
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS auth0_sub VARCHAR(128) UNIQUE
""")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auth0_sub")
