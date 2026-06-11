"""Classify user API keys by creation path.

Revision ID: 0105
Revises: 0104
"""

from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_api_keys
            ADD COLUMN key_type text NOT NULL DEFAULT 'manual',
            ADD CONSTRAINT user_api_keys_key_type_check
                CHECK (key_type IN ('password', 'manual', 'cli', 'invite'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_api_keys
            DROP CONSTRAINT IF EXISTS user_api_keys_key_type_check,
            DROP COLUMN IF EXISTS key_type
    """)
