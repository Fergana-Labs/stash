"""Workspace-registered upstream MCP servers for the MCP proxy.

Credentials (request headers) are Fernet-encrypted with the integrations
key. `tool_allowlist` is explicit and default-deny: an empty list exposes
nothing through the proxy.

Revision ID: 0107
Revises: 0106
"""

from alembic import op

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE workspace_mcp_servers (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id      uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            name              text NOT NULL,
            url               text NOT NULL,
            headers_encrypted bytea,
            tool_allowlist    jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, name)
        )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_mcp_servers")
