"""Store a display fragment for API keys.

Keys are stored hashed, so the console's key table had nothing to render but
the name — no Anthropic-style "st_z6apB…IX3g" fragment to tell two
"production" keys apart. New keys persist their first 8 and last 4 characters
at mint time; the hash remains the only full record of the key. Rows minted
before this migration stay NULL and render without a fragment.

Revision ID: 0194
Revises: 0193
"""

import sqlalchemy as sa
from alembic import op

revision = "0194"
down_revision = "0193"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_api_keys", sa.Column("key_prefix", sa.String(12), nullable=True))
    op.add_column("user_api_keys", sa.Column("key_suffix", sa.String(4), nullable=True))


def downgrade() -> None:
    op.drop_column("user_api_keys", "key_suffix")
    op.drop_column("user_api_keys", "key_prefix")
