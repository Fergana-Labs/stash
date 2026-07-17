"""X bookmarks become a synced, copied-content source.

Unlike the live `bookmarks` ref on a twitter source (one page, read on
demand), a twitter_bookmarks source archives every bookmark it has ever
seen: content is copied for FTS + embeddings and never deleted when a post
is un-bookmarked or ages past the API's first page — a diary, not a mirror.

Revision ID: 0146
Revises: 0145
"""

from alembic import op

revision = "0146"
down_revision = "0145"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE twitter_bookmark_docs (
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

            UNIQUE (source_id, path)
        )
    """)
    op.execute(
        "CREATE INDEX twitter_bookmark_docs_source_idx ON twitter_bookmark_docs (source_id, path) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX twitter_bookmark_docs_fts_idx ON twitter_bookmark_docs "
        "USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    op.execute(
        "CREATE INDEX twitter_bookmark_docs_embed_stale_idx ON twitter_bookmark_docs (id) "
        "WHERE embed_stale"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS twitter_bookmark_docs")
