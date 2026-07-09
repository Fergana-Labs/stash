"""Folder-scoped Google Drive becomes a copied-content source.

A Drive source used to be index-only: we stored the path and the Drive file id,
and fetched the body from Google on every read. That is untenable for a picked
folder of PDF catalogs — a 165-page catalog took 81 seconds to `cat`, anything
over 25 MB returned a placeholder sentence instead of text, and a scanned PDF
returned the empty string, because OCR only ever ran on uploaded files.

So a picked folder is now its own source type, `google_drive_folder`, backed by
`drive_documents`: a content table like `github_documents`. Its bodies are
extracted once at sync (OCR included) and every read is a Postgres row.

Whole-Drive sources keep `source_type = 'google_drive'` and stay index-only.
`root` crawls My Drive plus Shared-with-me plus every Shared Drive — unbounded,
and Google already full-text-indexes it. The guard is the type, not a branch.

Revision ID: 0141
Revises: 0140
"""

from alembic import op

revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE drive_documents (
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

            content       text,
            content_hash  text,
            embedding     vector(384),
            embed_stale   boolean NOT NULL DEFAULT FALSE,

            -- Extraction runs in a child process after the sync walk, so a row
            -- exists before its body does. `content` is NULL until the status is
            -- 'done', and a read of anything else fails loud rather than handing
            -- the agent an empty string.
            extraction_status   text NOT NULL DEFAULT 'pending',
            extraction_error    text,
            extraction_attempts integer NOT NULL DEFAULT 0,
            locked_at           timestamptz,

            UNIQUE (source_id, path)
        )
    """)
    op.execute(
        "CREATE INDEX drive_documents_source_idx ON drive_documents (source_id, path) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX drive_documents_fts_idx ON drive_documents "
        "USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    op.execute(
        "CREATE INDEX drive_documents_embed_stale_idx ON drive_documents (id) WHERE embed_stale"
    )
    op.execute(
        "CREATE INDEX drive_documents_extraction_idx ON drive_documents (extraction_status) "
        "WHERE deleted_at IS NULL"
    )

    # Existing picked folders become the new type in one shot. Their index rows
    # carry no bodies, so they are dropped: the next sync rebuilds them in
    # drive_documents and extracts each file.
    op.execute("""
        DELETE FROM drive_index
        WHERE source_id IN (
            SELECT id FROM user_sources
            WHERE source_type = 'google_drive' AND external_ref <> 'root'
        )
    """)
    op.execute("""
        UPDATE user_sources
        SET source_type = 'google_drive_folder', sync_status = 'idle', last_synced_at = NULL
        WHERE source_type = 'google_drive' AND external_ref <> 'root'
    """)


def downgrade() -> None:
    op.execute(
        "UPDATE user_sources SET source_type = 'google_drive' "
        "WHERE source_type = 'google_drive_folder'"
    )
    op.execute("DROP TABLE drive_documents")
