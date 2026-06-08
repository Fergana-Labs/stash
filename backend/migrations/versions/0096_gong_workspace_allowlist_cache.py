"""Store Gong workspace id on cached calls.

Revision ID: 0096
Revises: 0095
"""

from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE gong_documents ADD COLUMN gong_workspace_id text")
    op.execute(
        "CREATE INDEX gong_documents_workspace_allowlist_idx "
        "ON gong_documents (source_id, gong_workspace_id) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS gong_documents_workspace_allowlist_idx")
    op.execute("ALTER TABLE gong_documents DROP COLUMN IF EXISTS gong_workspace_id")
