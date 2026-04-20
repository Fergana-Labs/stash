"""Enforce (notebook_id, folder_id, name) uniqueness on notebook_pages.

Filesystem invariant: you can't have two `README.md` files in the same
folder. The schema allowed it; this migration closes the gap. Two
partial indexes handle the NULL-folder case cleanly without requiring
PG 15+ NULLS NOT DISTINCT.

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Pages inside a folder: unique on (notebook, folder, name).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_notebook_pages_unique_in_folder "
        "ON notebook_pages(notebook_id, folder_id, name) "
        "WHERE folder_id IS NOT NULL"
    )
    # Root-level pages (folder_id IS NULL): unique on (notebook, name).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_notebook_pages_unique_at_root "
        "ON notebook_pages(notebook_id, name) "
        "WHERE folder_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notebook_pages_unique_at_root")
    op.execute("DROP INDEX IF EXISTS idx_notebook_pages_unique_in_folder")
