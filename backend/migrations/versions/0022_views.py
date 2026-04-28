"""Curated Views — published subsets of a workspace.

A View is a hand-picked, ordered collection of resources (notebooks, tables,
files, decks, history events) drawn from a single workspace. The source
workspace can be private; the View is the only public surface.

Revision ID: 0022
Revises: 0021
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    slug VARCHAR(96) NOT NULL UNIQUE,
    title VARCHAR(160) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    owner_id UUID NOT NULL REFERENCES users(id),
    is_public BOOLEAN NOT NULL DEFAULT false,
    cover_image_url TEXT,
    view_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS view_items (
    view_id UUID NOT NULL REFERENCES views(id) ON DELETE CASCADE,
    object_type VARCHAR(16) NOT NULL
        CHECK(object_type IN ('notebook', 'table', 'file', 'deck', 'history')),
    object_id UUID NOT NULL,
    position INT NOT NULL DEFAULT 0,
    label_override VARCHAR(160),
    PRIMARY KEY (view_id, object_type, object_id)
)
""")

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_views_workspace ON views(workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_views_public_updated "
        "ON views(updated_at DESC) WHERE is_public = true"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_view_items_position ON view_items(view_id, position)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_view_items_position")
    op.execute("DROP INDEX IF EXISTS idx_views_public_updated")
    op.execute("DROP INDEX IF EXISTS idx_views_workspace")
    op.execute("DROP TABLE IF EXISTS view_items")
    op.execute("DROP TABLE IF EXISTS views")
