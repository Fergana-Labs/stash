"""User integrations (OAuth tokens for third-party providers).

Revision ID: 0061
Revises: 0060
"""

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No CHECK constraint on `provider` — providers self-register at runtime
    # via backend/integrations/registry.py. Adding a new provider must not
    # require a migration.
    op.execute(
        """
        CREATE TABLE user_integrations (
            user_id                 uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider                text NOT NULL,
            access_token_encrypted  bytea NOT NULL,
            refresh_token_encrypted bytea,
            scopes                  text[] NOT NULL DEFAULT '{}',
            expires_at              timestamptz,
            account_email           text,
            account_display_name    text,
            created_at              timestamptz NOT NULL DEFAULT now(),
            updated_at              timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, provider)
        )
        """
    )
    op.execute(
        "CREATE INDEX user_integrations_provider_idx ON user_integrations (provider)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_integrations")
