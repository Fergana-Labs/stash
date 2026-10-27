"""Separate customer-managed developer keys from internal infrastructure keys.

The old ``machine`` type covered both Developer Platform credentials and keys
installed inside cloud computers. That made internal credentials visible and
revocable through customer-facing key APIs. Move cloud-computer credentials to
``internal``, move every other machine credential to ``developer``, and remove
the ambiguous type. Existing duplicate cloud-computer keys are revoked while
the newest credential for each user remains live.

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
        ALTER TABLE user_api_keys DROP CONSTRAINT user_api_keys_key_type_check
        """
    )
    op.execute(
        """
        UPDATE user_api_keys
        SET key_type = CASE
            WHEN name IN ('cloud computer', 'local sprite') THEN 'internal'
            ELSE 'developer'
        END
        WHERE key_type = 'machine'
        """
    )
    op.execute(
        """
        UPDATE user_api_keys SET revoked_at = now()
        WHERE key_type = 'internal' AND name = 'cloud computer' AND revoked_at IS NULL
          AND id NOT IN (
            SELECT DISTINCT ON (user_id) id FROM user_api_keys
            WHERE key_type = 'internal' AND name = 'cloud computer' AND revoked_at IS NULL
            ORDER BY user_id, created_at DESC, id DESC
          )
        """
    )
    op.execute(
        """
        ALTER TABLE user_api_keys
            ADD CONSTRAINT user_api_keys_key_type_check
            CHECK (key_type IN (
                'password', 'manual', 'cli', 'invite', 'developer', 'internal'
            ))
        """
    )


def downgrade() -> None:
    pass
