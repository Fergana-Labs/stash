"""Link uploaded files to materialized tables (CSV ingest).

Adds files.linked_table_id so a CSV uploaded as a blob can be parsed once
into a real Table and any future click on that file routes to the live
tables editor instead of a bespoke viewer.

Revision ID: 0029
Revises: 0028
"""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE files ADD COLUMN linked_table_id UUID REFERENCES tables(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX idx_files_linked_table ON files(linked_table_id) "
        "WHERE linked_table_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_files_linked_table")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS linked_table_id")
