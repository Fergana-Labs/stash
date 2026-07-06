"""Sources: a unified source layer for agent access to company data.

Two new tables:

- `workspace_sources` — the registry of connected sources (one row per added
  GitHub repo / Drive / Notion / Slack / Granola). Native sources (the file
  system, session transcripts) are virtual and never stored here. Connected
  sources are USER-SCOPED: `owner_user_id` is both the visibility owner and the
  credential owner (sync uses that user's OAuth token).
- `source_documents` — the dedicated index store for connected-source content,
  kept separate from `pages`/`files` so external content never inherits
  native-only machinery (comments, collab, stash-sharing). Navigable sources
  store a tree (`path` like "docs/api.md"); streaming sources store synthetic
  paths ("#eng/2026-05-30/1717.ts"). FTS + pgvector mirror pages/files so the
  agent's `search` tool spans every source.

No CHECK constraint on `source_type` — source types self-register at runtime
like providers do, so adding one must not require a migration.

Revision ID: 0080
Revises: 0079
"""

from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE workspace_sources (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id    uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            owner_user_id   uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_type     text NOT NULL,
            external_ref    text NOT NULL,
            display_name    text NOT NULL,
            capability      text NOT NULL DEFAULT 'navigable',
            sync_enabled    boolean NOT NULL DEFAULT TRUE,
            sync_interval_s integer NOT NULL DEFAULT 3600,
            sync_cursor     text,
            sync_status     text NOT NULL DEFAULT 'idle',
            sync_error      text,
            last_synced_at  timestamptz,
            next_sync_at    timestamptz NOT NULL DEFAULT now(),
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, owner_user_id, source_type, external_ref)
        )
        """)
    # Beat's reconcile_due() scans for pull sources whose next sync is due.
    op.execute(
        "CREATE INDEX workspace_sources_due_idx "
        "ON workspace_sources (next_sync_at) WHERE sync_enabled"
    )
    # The sidebar + agent list a user's own connected sources in a workspace.
    op.execute(
        "CREATE INDEX workspace_sources_owner_idx "
        "ON workspace_sources (workspace_id, owner_user_id)"
    )

    op.execute("""
        CREATE TABLE source_documents (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id        uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            source_id           uuid NOT NULL REFERENCES workspace_sources(id) ON DELETE CASCADE,
            path                text NOT NULL,
            name                text NOT NULL,
            kind                text NOT NULL DEFAULT 'file',
            content             text,
            content_hash        text,
            blob_storage_key    text,
            external_ref        text,
            external_updated_at timestamptz,
            embedding           vector(384),
            embed_stale         boolean NOT NULL DEFAULT FALSE,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            deleted_at          timestamptz,
            UNIQUE (source_id, path)
        )
        """)
    # Listing a directory in a source = prefix scan over live rows.
    op.execute(
        "CREATE INDEX source_documents_source_idx "
        "ON source_documents (source_id, path) WHERE deleted_at IS NULL"
    )
    # Full-text search across a source's content (matches the history_events
    # FTS shape: to_tsvector('english', content) @@ websearch_to_tsquery).
    op.execute(
        "CREATE INDEX source_documents_fts_idx "
        "ON source_documents USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    # Semantic search hot path, mirroring pages/files.
    op.execute(
        "CREATE INDEX source_documents_embed_stale_idx ON source_documents (id) WHERE embed_stale"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_documents")
    op.execute("DROP TABLE IF EXISTS workspace_sources")
