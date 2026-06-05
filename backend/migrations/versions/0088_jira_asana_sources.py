"""Per-integration source tables for Jira and Asana.

Both are copied-content sources (FTS + embeddings live in the table), same
shape as github_documents (migration 0084): Jira issues and Asana tasks each
become a document keyed by (source_id, path).

Revision ID: 0088
Revises: 0087
"""

from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

_BASE_COLUMNS = """
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_id           uuid NOT NULL REFERENCES workspace_sources(id) ON DELETE CASCADE,
    path                text NOT NULL,
    name                text NOT NULL,
    kind                text NOT NULL DEFAULT 'file',
    external_ref        text,
    external_updated_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    content             text,
    content_hash        text,
    embedding           vector(384),
    embed_stale         boolean NOT NULL DEFAULT FALSE
"""

_TABLES = ("jira_documents", "asana_documents")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"CREATE TABLE {table} ({_BASE_COLUMNS}, UNIQUE (source_id, path))")
        op.execute(
            f"CREATE INDEX {table}_source_idx ON {table} (source_id, path) "
            f"WHERE deleted_at IS NULL"
        )
        op.execute(
            f"CREATE INDEX {table}_fts_idx ON {table} "
            f"USING gin (to_tsvector('english', coalesce(content, '')))"
        )
        op.execute(f"CREATE INDEX {table}_embed_stale_idx ON {table} (id) WHERE embed_stale")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")
