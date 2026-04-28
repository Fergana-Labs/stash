"""Add catalog metadata to workspaces for public discovery and forking.

Revision ID: 0021
Revises: 0020
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS summary VARCHAR(280)")
    op.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS category VARCHAR(32)")
    op.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS featured BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS cover_image_url TEXT")
    op.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS fork_count INT NOT NULL DEFAULT 0")
    op.execute(
        "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS forked_from_workspace_id "
        "UUID REFERENCES workspaces(id) ON DELETE SET NULL"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS workspaces_public_featured "
        "ON workspaces (featured DESC, updated_at DESC) WHERE is_public = true"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS workspaces_public_category "
        "ON workspaces (category) WHERE is_public = true"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS workspaces_tags_gin ON workspaces USING gin (tags)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS workspaces_tags_gin")
    op.execute("DROP INDEX IF EXISTS workspaces_public_category")
    op.execute("DROP INDEX IF EXISTS workspaces_public_featured")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS forked_from_workspace_id")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS fork_count")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS cover_image_url")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS featured")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS tags")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS summary")
