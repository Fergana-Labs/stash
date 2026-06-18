"""Publishable (anon) API keys for public/shared dashboards.

A `pk_` key is workspace-scoped and safe to embed in browser JS. It grants
nothing on its own — access is decided by `shares` rows with
principal_type='api_key' and principal_id = the key's id (read-only by default;
a write policy is an explicit row). `shares.principal_type` is free text, so no
constraint change is needed there.

Revision ID: 0118
Revises: 0117
"""

from alembic import op

revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE publishable_keys (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            key_hash varchar(64) NOT NULL UNIQUE,
            name varchar(128) NOT NULL DEFAULT 'default',
            created_by uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_used_at timestamptz,
            revoked_at timestamptz
        )
        """)
    op.execute("CREATE INDEX publishable_keys_workspace_idx ON publishable_keys (workspace_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS publishable_keys")
