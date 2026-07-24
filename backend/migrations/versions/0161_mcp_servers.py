"""Per-user MCP server registry backing the Tools page and `stash tools`.

Each row is one MCP server the user registered: stdio servers carry a
command (plus optional env), http servers carry a URL (plus optional
headers). Secrets (headers/env) are Fernet-encrypted with the integrations
keyring — the same at-rest scheme as integration OAuth tokens.

Revision ID: 0161
Revises: 0160
"""

from alembic import op

revision = "0161"
down_revision = "0160"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE mcp_servers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            transport text NOT NULL CHECK (transport IN ('stdio', 'http')),
            command text,
            url text,
            headers_encrypted bytea,
            env_encrypted bytea,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (owner_user_id, name)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE mcp_servers")
