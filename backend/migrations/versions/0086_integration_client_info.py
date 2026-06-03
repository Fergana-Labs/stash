"""Store dynamic-client-registration info on user_integrations.

Granola authenticates against its MCP server with OAuth 2.0 Dynamic Client
Registration (DCR): there is no pre-shared client_id/secret — we register a
client per user at connect time and must keep that registration to refresh the
token later. The registered client (an RFC 7591 response) lives in `client_info`.
Null for every provider that uses a static OAuth client (Google/GitHub/…).

Revision ID: 0086
Revises: 0085
"""

from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_integrations ADD COLUMN client_info jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE user_integrations DROP COLUMN IF EXISTS client_info")
