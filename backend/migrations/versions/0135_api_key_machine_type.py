"""Allow the 'machine' API key type used by cloud computer provisioning.

Revision ID: 0135
Revises: 0134
"""

from alembic import op

revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_api_keys
            DROP CONSTRAINT user_api_keys_key_type_check,
            ADD CONSTRAINT user_api_keys_key_type_check
                CHECK (key_type IN ('password', 'manual', 'cli', 'invite', 'machine'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_api_keys
            DROP CONSTRAINT user_api_keys_key_type_check,
            ADD CONSTRAINT user_api_keys_key_type_check
                CHECK (key_type IN ('password', 'manual', 'cli', 'invite'))
    """)
