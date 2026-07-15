"""Instagram saves: extension-pushed save lists, hydrated via ScrapeCreators.

The browser extension pushes the user's saved-post URLs as skeleton rows
(hydration_status='pending'); the indexer fills content + transcript and
archives the media itself into object storage — a save must survive the
post being deleted or the account going private. Archive semantics:
rows are never deleted by sync.

Revision ID: 0147
Revises: 0146
"""

from alembic import op

revision = "0147"
down_revision = "0146"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE instagram_save_docs (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id           uuid NOT NULL REFERENCES user_sources(id) ON DELETE CASCADE,
            path                text NOT NULL,
            name                text NOT NULL,
            kind                text NOT NULL DEFAULT 'post',
            external_ref        text,
            external_updated_at timestamptz,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            deleted_at          timestamptz,

            content       text,
            content_hash  text,
            embedding     vector(384),
            embed_stale   boolean NOT NULL DEFAULT FALSE,

            saved_at            timestamptz,
            media_storage_key   text,
            media_content_type  text,

            -- Rows are inserted as skeletons by the push endpoint and filled
            -- by the indexer; content is NULL until hydration_status = 'done'
            -- and a read of anything else fails loud.
            hydration_status    text NOT NULL DEFAULT 'pending',
            hydration_error     text,
            hydration_attempts  integer NOT NULL DEFAULT 0,

            UNIQUE (source_id, path)
        )
    """)
    op.execute(
        "CREATE INDEX instagram_save_docs_source_idx ON instagram_save_docs (source_id, path) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX instagram_save_docs_fts_idx ON instagram_save_docs "
        "USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    op.execute(
        "CREATE INDEX instagram_save_docs_embed_stale_idx ON instagram_save_docs (id) "
        "WHERE embed_stale"
    )
    op.execute(
        "CREATE INDEX instagram_save_docs_hydration_idx ON instagram_save_docs (hydration_status) "
        "WHERE hydration_status IN ('pending', 'failed')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS instagram_save_docs")
