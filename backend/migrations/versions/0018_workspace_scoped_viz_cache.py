"""Add workspace_id to viz cache tables so workspace-scoped visualizations
can reuse the persistent caches instead of bypassing them.

NULL workspace_id still represents the user-wide cache row (what the
`/me/*` endpoints return with no ?workspace_id=). Postgres 16's NULLS
NOT DISTINCT semantics make the unique index treat NULLs as equal, so
there's still exactly one user-wide row per (user_id, source_type).

Revision ID: 0018
Revises: 0017
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- knowledge_density_cache ---
    op.execute(
        "ALTER TABLE knowledge_density_cache "
        "ADD COLUMN IF NOT EXISTS workspace_id UUID "
        "REFERENCES workspaces(id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE knowledge_density_cache DROP CONSTRAINT IF EXISTS knowledge_density_cache_pkey"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS knowledge_density_cache_scope_key "
        "ON knowledge_density_cache(user_id, workspace_id) NULLS NOT DISTINCT"
    )

    # --- embedding_projections ---
    op.execute(
        "ALTER TABLE embedding_projections "
        "ADD COLUMN IF NOT EXISTS workspace_id UUID "
        "REFERENCES workspaces(id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE embedding_projections DROP CONSTRAINT IF EXISTS embedding_projections_pkey"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS embedding_projections_scope_key "
        "ON embedding_projections(user_id, source_type, workspace_id) NULLS NOT DISTINCT"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS embedding_projections_scope_key")
    op.execute("ALTER TABLE embedding_projections DROP COLUMN IF EXISTS workspace_id")
    op.execute(
        "ALTER TABLE embedding_projections "
        "ADD CONSTRAINT embedding_projections_pkey PRIMARY KEY (user_id, source_type)"
    )

    op.execute("DROP INDEX IF EXISTS knowledge_density_cache_scope_key")
    op.execute("ALTER TABLE knowledge_density_cache DROP COLUMN IF EXISTS workspace_id")
    op.execute(
        "ALTER TABLE knowledge_density_cache "
        "ADD CONSTRAINT knowledge_density_cache_pkey PRIMARY KEY (user_id)"
    )
