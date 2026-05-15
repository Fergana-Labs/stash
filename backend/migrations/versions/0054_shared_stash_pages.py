"""Let shared Stash pages skip Filesystem name uniqueness.

Revision ID: 0054
Revises: 0053
"""

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_in_folder")
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_at_root")
    op.execute("""
CREATE UNIQUE INDEX idx_pages_unique_in_folder
ON pages(workspace_id, folder_id, name)
WHERE folder_id IS NOT NULL AND COALESCE(metadata->>'shared_in_stash_id', '') = ''
""")
    op.execute("""
CREATE UNIQUE INDEX idx_pages_unique_at_root
ON pages(workspace_id, name)
WHERE folder_id IS NULL AND COALESCE(metadata->>'shared_in_stash_id', '') = ''
""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_in_folder")
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_at_root")
    op.execute("""
CREATE UNIQUE INDEX idx_pages_unique_in_folder
ON pages(workspace_id, folder_id, name)
WHERE folder_id IS NOT NULL
""")
    op.execute("""
CREATE UNIQUE INDEX idx_pages_unique_at_root
ON pages(workspace_id, name)
WHERE folder_id IS NULL
""")
