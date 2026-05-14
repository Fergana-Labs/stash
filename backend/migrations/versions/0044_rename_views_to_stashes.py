"""Rename product Stash storage tables.

Revision ID: 0044
Revises: 0043
"""

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE views RENAME TO stashes")
    op.execute("ALTER TABLE view_items RENAME TO stash_items")
    op.execute("ALTER TABLE stash_items RENAME COLUMN view_id TO stash_id")
    op.execute(
        "ALTER TABLE stash_items RENAME CONSTRAINT view_items_object_type_check "
        "TO stash_items_object_type_check"
    )
    op.execute("ALTER INDEX IF EXISTS idx_views_workspace RENAME TO idx_stashes_workspace")
    op.execute("ALTER INDEX IF EXISTS idx_public_views_recent RENAME TO idx_public_stashes_recent")
    op.execute("ALTER INDEX IF EXISTS idx_view_items_position RENAME TO idx_stash_items_position")


def downgrade() -> None:
    op.execute("ALTER INDEX IF EXISTS idx_stash_items_position RENAME TO idx_view_items_position")
    op.execute("ALTER INDEX IF EXISTS idx_public_stashes_recent RENAME TO idx_public_views_recent")
    op.execute("ALTER INDEX IF EXISTS idx_stashes_workspace RENAME TO idx_views_workspace")
    op.execute(
        "ALTER TABLE stash_items RENAME CONSTRAINT stash_items_object_type_check "
        "TO view_items_object_type_check"
    )
    op.execute("ALTER TABLE stash_items RENAME COLUMN stash_id TO view_id")
    op.execute("ALTER TABLE stash_items RENAME TO view_items")
    op.execute("ALTER TABLE stashes RENAME TO views")
