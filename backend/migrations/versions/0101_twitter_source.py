"""Add Twitter / X source table.

Twitter stores recent-search result metadata in `twitter_posts`. Search runs
live against X, personal refs are fetched live through OAuth user context, and
post bodies are fetched lazily when a result is opened.

Revision ID: 0101
Revises: 0100
"""

from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None

_BASE_COLUMNS = """
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_id           uuid NOT NULL REFERENCES workspace_sources(id) ON DELETE CASCADE,
    path                text NOT NULL,
    name                text NOT NULL,
    kind                text NOT NULL DEFAULT 'post',
    external_ref        text,
    external_updated_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    UNIQUE (source_id, path)
"""


def upgrade() -> None:
    # No extra (source_id, path) index: the UNIQUE constraint already provides
    # the btree the upsert's ON CONFLICT and lookups use.
    op.execute(f"CREATE TABLE twitter_posts ({_BASE_COLUMNS})")
    # Sources with no indexer must not sit in the sync queue: the reconciler
    # skips them without advancing next_sync_at, so an enabled row stays "due"
    # forever and starves real syncs out of the due_sources window. Snowflake
    # rows predate this fix (create_source now disables sync for such types).
    op.execute("UPDATE workspace_sources SET sync_enabled = false WHERE source_type = 'snowflake'")


def downgrade() -> None:
    # The snowflake sync_enabled flip is deliberately not reverted: restoring
    # true would re-introduce the queue starvation, and per-row prior state
    # (default vs user-disabled) was never recorded.
    op.execute("DROP TABLE IF EXISTS twitter_posts")
