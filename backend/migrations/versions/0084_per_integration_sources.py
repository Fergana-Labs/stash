"""Per-integration source storage: drop the unified source_documents.

`source_documents` tried to be one table for every connected source. That
forces every integration to share one shape and one set of machinery. Replace
it with one table per integration, grouped by storage strategy:

- **Copied content** (FTS + embeddings live here): `github_documents` (repo tree,
  navigable like a filesystem), `slack_messages` (own columns, fed by webhook +
  backfill), `granola_notes` (own columns, scheduled pull).
- **Index only** (content fetched lazily from the provider at read time using the
  owner's token): `drive_index`, `notion_index` — they hold just the path/name +
  the provider's `external_ref`, never the document body.

Every table shares a navigation shape — `path`, `name`, `kind`, `deleted_at` —
so the agent's list/read tools stay uniform across sources. The content tables
add `content`/`content_hash`/`embedding`/`embed_stale`; Slack keeps its native
`channel_id`/`channel_name`/`ts`.

Revision ID: 0084
Revises: 0083
"""

from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def _base_columns() -> str:
    """The navigation shape every per-integration table shares."""
    return """
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
        deleted_at          timestamptz
    """


def _content_columns() -> str:
    """Copied-content tables also store the body, its hash, and an embedding."""
    return """
        content       text,
        content_hash  text,
        embedding     vector(384),
        embed_stale   boolean NOT NULL DEFAULT FALSE
    """


def _content_indexes(table: str) -> None:
    op.execute(
        f"CREATE INDEX {table}_source_idx ON {table} (source_id, path) WHERE deleted_at IS NULL"
    )
    op.execute(
        f"CREATE INDEX {table}_fts_idx ON {table} "
        f"USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    op.execute(f"CREATE INDEX {table}_embed_stale_idx ON {table} (id) WHERE embed_stale")


def _index_only_indexes(table: str) -> None:
    op.execute(
        f"CREATE INDEX {table}_source_idx ON {table} (source_id, path) WHERE deleted_at IS NULL"
    )


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_documents")

    # --- copied content (FTS + embeddings) ---------------------------------
    op.execute(f"""
        CREATE TABLE github_documents (
            {_base_columns()},
            {_content_columns()},
            UNIQUE (source_id, path)
        )
    """)
    _content_indexes("github_documents")

    op.execute(f"""
        CREATE TABLE slack_messages (
            {_base_columns()},
            {_content_columns()},
            channel_id   text,
            channel_name text,
            ts           text,
            UNIQUE (source_id, path)
        )
    """)
    _content_indexes("slack_messages")

    op.execute(f"""
        CREATE TABLE granola_notes (
            {_base_columns()},
            {_content_columns()},
            UNIQUE (source_id, path)
        )
    """)
    _content_indexes("granola_notes")

    # --- index only (content fetched lazily) -------------------------------
    op.execute(f"""
        CREATE TABLE drive_index (
            {_base_columns()},
            UNIQUE (source_id, path)
        )
    """)
    _index_only_indexes("drive_index")

    op.execute(f"""
        CREATE TABLE notion_index (
            {_base_columns()},
            UNIQUE (source_id, path)
        )
    """)
    _index_only_indexes("notion_index")


def downgrade() -> None:
    for table in (
        "github_documents",
        "slack_messages",
        "granola_notes",
        "drive_index",
        "notion_index",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
