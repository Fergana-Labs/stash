"""X (Twitter) saves: extension-captured links, hydrated via twitterapi.io.

Replaces the OAuth/bring-your-own-app X integration. The browser extension
captures the links of your bookmarks / posts / replies / articles on x.com;
the indexer hydrates each via twitterapi.io — storing the full tweet text,
the conversation root for reply context, and archiving the images/video into
object storage so the save survives the tweet being deleted.

Also drops the tables from the removed OAuth path: twitter_app_credentials
(bring-your-own-app creds) and twitter_bookmark_docs (X-API bookmarks).

Revision ID: 0153
Revises: 0152
"""

from alembic import op

revision = "0153"
down_revision = "0152"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE x_save_docs (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id           uuid NOT NULL REFERENCES user_sources(id) ON DELETE CASCADE,
            path                text NOT NULL,
            name                text NOT NULL,
            kind                text NOT NULL DEFAULT 'Bookmark',
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
            -- A tweet can carry up to 4 images or a video; each archived blob is
            -- {storage_key, content_type}.
            media               jsonb NOT NULL DEFAULT '[]'::jsonb,

            hydration_status    text NOT NULL DEFAULT 'pending',
            hydration_error     text,
            hydration_attempts  integer NOT NULL DEFAULT 0,

            UNIQUE (source_id, path)
        )
    """)
    op.execute(
        "CREATE INDEX x_save_docs_source_idx ON x_save_docs (source_id, path) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX x_save_docs_fts_idx ON x_save_docs "
        "USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    op.execute("CREATE INDEX x_save_docs_embed_stale_idx ON x_save_docs (id) WHERE embed_stale")
    op.execute(
        "CREATE INDEX x_save_docs_hydration_idx ON x_save_docs (hydration_status) "
        "WHERE hydration_status IN ('pending', 'failed')"
    )

    # Tables + source rows from the removed OAuth / bring-your-own-app X path.
    op.execute("DROP TABLE IF EXISTS twitter_app_credentials")
    op.execute("DROP TABLE IF EXISTS twitter_bookmark_docs")
    op.execute("DROP TABLE IF EXISTS twitter_posts")
    op.execute("DELETE FROM user_sources WHERE source_type IN ('twitter', 'twitter_bookmarks')")
    op.execute("DELETE FROM user_integrations WHERE provider = 'twitter'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS x_save_docs")
