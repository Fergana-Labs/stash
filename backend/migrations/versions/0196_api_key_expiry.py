"""API keys can expire.

`expires_at` NULL means the key never expires — every existing key keeps
working. An expired key is refused at auth time like a revoked one, but the
row keeps its timestamp so the console can say "expired" instead of the key
just vanishing.

Revision ID: 0196
Revises: 0195
"""

from alembic import op

revision = "0196"
down_revision = "0195"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_api_keys ADD COLUMN expires_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE user_api_keys DROP COLUMN IF EXISTS expires_at")
