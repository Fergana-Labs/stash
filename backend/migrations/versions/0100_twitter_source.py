"""Add Twitter / X source table.

Twitter stores recent-search result metadata in `twitter_posts`. Search runs
live against X, and post bodies are fetched lazily when a result is opened.

Revision ID: 0100
Revises: 0099
"""

from alembic import op

revision = "0100"
down_revision = "0099"
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


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS twitter_posts")
