"""Revoke orphaned "cloud computer" API keys.

Sprite provisioning minted a fresh machine key on every provision and reseed
without revoking the one it replaced, and failed provisions leaked their key
too — Heavi's console showed five identical "cloud computer" keys. A box only
ever holds the key from its last successful seed, which is the newest one, so
for each user the newest unrevoked "cloud computer" key stays and the rest are
revoked. Provisioning now revokes superseded keys itself.

Revision ID: 0203
Revises: 0202
"""

from alembic import op

revision = "0203"
down_revision = "0202"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE user_api_keys SET revoked_at = now()
        WHERE key_type = 'machine' AND name = 'cloud computer' AND revoked_at IS NULL
          AND id NOT IN (
            SELECT DISTINCT ON (user_id) id FROM user_api_keys
            WHERE key_type = 'machine' AND name = 'cloud computer' AND revoked_at IS NULL
            ORDER BY user_id, created_at DESC
          )
        """
    )


def downgrade() -> None:
    pass
