"""Jira & Asana become index-only (search federated to the provider).

We stopped copying issue/task bodies: Jira search is federated to JQL and Asana
to its tasks/search endpoint, with bodies fetched lazily on read. So drop the
copied-content columns + their FTS/embedding indexes from jira_documents and
asana_documents, leaving the navigable index (path/name/external_ref). The
source_idx + UNIQUE(source_id, path) stay.

Revision ID: 0091
Revises: 0090
"""

from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

_TABLES = ("jira_documents", "asana_documents")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS {table}_fts_idx")
        op.execute(f"DROP INDEX IF EXISTS {table}_embed_stale_idx")
        op.execute(
            f"ALTER TABLE {table} "
            f"DROP COLUMN content, DROP COLUMN content_hash, "
            f"DROP COLUMN embedding, DROP COLUMN embed_stale"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD COLUMN content text, ADD COLUMN content_hash text, "
            f"ADD COLUMN embedding vector(384), "
            f"ADD COLUMN embed_stale boolean NOT NULL DEFAULT FALSE"
        )
        op.execute(
            f"CREATE INDEX {table}_fts_idx ON {table} "
            f"USING gin (to_tsvector('english', coalesce(content, '')))"
        )
        op.execute(f"CREATE INDEX {table}_embed_stale_idx ON {table} (id) WHERE embed_stale")
