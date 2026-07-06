"""Memory folder — a reserved system folder per user.

Memory is its own space, distinct from Files: one folder per owner flagged
``is_memory``. It's created on demand, hidden from the Files tree, and can't be
renamed, moved, or deleted. A partial unique index enforces one per owner.

Revision ID: 0124
Revises: 0123
"""

from alembic import op

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE folders ADD COLUMN is_memory boolean NOT NULL DEFAULT false")
    op.execute(
        "CREATE UNIQUE INDEX idx_folders_one_memory_per_owner "
        "ON folders (owner_user_id) WHERE is_memory"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_folders_one_memory_per_owner")
    op.execute("ALTER TABLE folders DROP COLUMN IF EXISTS is_memory")
