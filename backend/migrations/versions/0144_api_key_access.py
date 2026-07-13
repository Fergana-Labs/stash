"""Access level on API keys: 'read' (reads + transcript upload) or 'full'.

Revision ID: 0144
Revises: 0143
"""

from alembic import op

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_api_keys
            ADD COLUMN access text NOT NULL DEFAULT 'full'
                CHECK (access IN ('read', 'full'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_api_keys
            DROP COLUMN access
    """)
