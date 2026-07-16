"""Per-integration source table for Attio call recordings.

Copied-content source (FTS + embeddings live in the table), same shape as
gong_documents: each Attio call recording's transcript becomes a document keyed
by (source_id, path).

Revision ID: 0152
Revises: 0151
"""

from alembic import op

revision = "0152"
down_revision = "0151"
branch_labels = None
depends_on = None

_COLUMNS = """
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id           uuid NOT NULL REFERENCES user_sources(id) ON DELETE CASCADE,
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
    op.execute(f"CREATE TABLE attio_documents ({_COLUMNS}, UNIQUE (source_id, path))")
    op.execute(
        "CREATE INDEX attio_documents_source_idx ON attio_documents (source_id, path) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX attio_documents_fts_idx ON attio_documents "
        "USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    op.execute(
        "CREATE INDEX attio_documents_embed_stale_idx ON attio_documents (id) WHERE embed_stale"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS attio_documents")
