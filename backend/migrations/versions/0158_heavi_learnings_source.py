"""Heavi rules-of-the-road source docs.

Copied-content table: each row mirrors one Heavi learning ("rule of the
road") so FTS and the embedding pipeline pick it up. VFS ls/cat never read
this table — they fetch the customer's endpoint live; this copy exists only
for search and the wiki.

Revision ID: 0158
Revises: 0157
"""

from alembic import op

revision = "0158"
down_revision = "0157"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE heavi_learning_docs (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id           uuid NOT NULL REFERENCES user_sources(id) ON DELETE CASCADE,
            path                text NOT NULL,
            name                text NOT NULL,
            kind                text NOT NULL,
            external_ref        text NOT NULL,
            external_updated_at timestamptz,
            content             text,
            content_hash        text,
            embedding           vector(384),
            embed_stale         boolean NOT NULL DEFAULT FALSE,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            deleted_at          timestamptz,
            UNIQUE (source_id, path)
        )
        """)
    op.execute(
        "CREATE INDEX heavi_learning_docs_source_idx ON heavi_learning_docs (source_id, path) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX heavi_learning_docs_fts_idx ON heavi_learning_docs "
        "USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    op.execute(
        "CREATE INDEX heavi_learning_docs_embed_stale_idx ON heavi_learning_docs (id) "
        "WHERE embed_stale"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS heavi_learning_docs")
