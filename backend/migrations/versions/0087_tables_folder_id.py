"""Add folder_id to tables so tables can live inside folders.

Tables were the one workspace content type that couldn't be organized into
folders (pages and files both gained folder_id earlier — see 0035). This
brings tables to parity: a table can sit at the workspace root or inside a
folder, and folder shares cascade to the tables within them.

Revision ID: 0087
Revises: 0086
"""

from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tables "
        "ADD COLUMN IF NOT EXISTS folder_id UUID "
        "REFERENCES folders(id) ON DELETE SET NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_tables_folder ON tables(folder_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tables_folder")
    op.execute("ALTER TABLE tables DROP COLUMN IF EXISTS folder_id")
