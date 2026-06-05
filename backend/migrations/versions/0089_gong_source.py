"""Per-integration source table for Gong.

Copied-content source (FTS + embeddings live in the table), same shape as
github_documents (migration 0084): each Gong call's transcript becomes a
document keyed by (source_id, path).

Revision ID: 0089
Revises: 0088
"""

from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None

_COLUMNS = """
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


def upgrade() -> None:
    op.execute(f"CREATE TABLE gong_documents ({_COLUMNS}, UNIQUE (source_id, path))")
    op.execute(
        "CREATE INDEX gong_documents_source_idx ON gong_documents (source_id, path) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX gong_documents_fts_idx ON gong_documents "
        "USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    op.execute("CREATE INDEX gong_documents_embed_stale_idx ON gong_documents (id) WHERE embed_stale")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gong_documents")
