"""Add indexes for CRUD hot paths.

Revision ID: 0074
Revises: 0073
Create Date: 2026-05-21
"""

from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tables_workspace_updated
        ON tables(workspace_id, updated_at DESC)
        WHERE workspace_id IS NOT NULL
        """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_folders_workspace_parent_name
        ON folders(workspace_id, parent_folder_id, name)
        """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pages_workspace_active_folder_name
        ON pages(workspace_id, folder_id, name)
        WHERE deleted_at IS NULL
          AND COALESCE(metadata->>'shared_in_stash_id', '') = ''
        """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_files_workspace_active_created
        ON files(workspace_id, created_at DESC)
        WHERE deleted_at IS NULL
        """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_files_folder_active_created
        ON files(folder_id, created_at DESC)
        WHERE deleted_at IS NULL
        """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_files_folder_active_created")
    op.execute("DROP INDEX IF EXISTS idx_files_workspace_active_created")
    op.execute("DROP INDEX IF EXISTS idx_pages_workspace_active_folder_name")
    op.execute("DROP INDEX IF EXISTS idx_folders_workspace_parent_name")
    op.execute("DROP INDEX IF EXISTS idx_tables_workspace_updated")
