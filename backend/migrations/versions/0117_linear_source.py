"""Add Linear source table.

Linear becomes a navigable, index-only source: `linear_index` holds one row per
issue (identifier + title), search is federated live to Linear's API, and the
issue body (description) is fetched lazily when a result is opened. This is in
addition to the existing session-label enrichment, which is unchanged.

Revision ID: 0117
Revises: 0116
"""

from alembic import op

revision = "0117"
down_revision = "0116"
branch_labels = None
depends_on = None

_BASE_COLUMNS = """
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_id           uuid NOT NULL REFERENCES workspace_sources(id) ON DELETE CASCADE,
    path                text NOT NULL,
    name                text NOT NULL,
    kind                text NOT NULL DEFAULT 'issue',
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
    op.execute(f"CREATE TABLE linear_index ({_BASE_COLUMNS})")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS linear_index")
