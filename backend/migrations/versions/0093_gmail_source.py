"""Add Gmail index-only source table.

Gmail stores message metadata only in `gmail_index`. Search is federated to
Gmail and message bodies are fetched lazily when a user opens a result.

Revision ID: 0093
Revises: 0092
"""

from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None

_BASE_COLUMNS = """
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_id           uuid NOT NULL REFERENCES workspace_sources(id) ON DELETE CASCADE,
    path                text NOT NULL,
    name                text NOT NULL,
    kind                text NOT NULL DEFAULT 'message',
    external_ref        text,
    external_updated_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    UNIQUE (source_id, path)
"""


def upgrade() -> None:
    op.execute(f"CREATE TABLE gmail_index ({_BASE_COLUMNS})")
    op.execute(
        "CREATE INDEX gmail_index_source_idx "
        "ON gmail_index (source_id, path) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gmail_index")
