"""Bring-your-own model credentials for the cloud agent.

A user connects a harness they own — Claude Code or Codex — via an API key or
an OAuth token. That credential runs as their harness on their sprite. Users
with no credential fall back to the managed agent (opencode + OpenRouter GLM)
on the Pro tier.

Revision ID: 0131
Revises: 0130
"""

from alembic import op

revision = "0131"
down_revision = "0130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_agent_credentials (
            user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider    text NOT NULL,               -- 'anthropic' | 'openai'
            kind        text NOT NULL,               -- 'api_key' | 'oauth'
            secret_enc  bytea NOT NULL,              -- Fernet-encrypted key or OAuth JSON
            created_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, provider)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_agent_credentials")
