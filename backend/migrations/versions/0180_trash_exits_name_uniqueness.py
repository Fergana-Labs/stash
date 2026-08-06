"""Trashed pages leave name uniqueness.

Folder deletion trashes the folder's pages, then the ON DELETE SET NULL FK
moves them to the scope root. With uniqueness enforced over trashed rows too,
the second same-named trashed page arriving at root violates
idx_pages_unique_at_root — so deleting two skills back-to-back 500'd (each
skill trashes a SKILL.md; found in prod on 2026-08-06). Uniqueness is a
live-namespace concern: scope both indexes to deleted_at IS NULL so trash can
hold any number of same-named pages.

Revision ID: 0180
Revises: 0179
"""

from alembic import op

revision = "0180"
down_revision = "0179"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_in_folder")
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_at_root")
    op.execute("""
CREATE UNIQUE INDEX idx_pages_unique_in_folder
ON pages(owner_user_id, folder_id, name)
WHERE folder_id IS NOT NULL AND deleted_at IS NULL
""")
    op.execute("""
CREATE UNIQUE INDEX idx_pages_unique_at_root
ON pages(owner_user_id, name)
WHERE folder_id IS NULL AND deleted_at IS NULL
""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_in_folder")
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_at_root")
    op.execute("""
CREATE UNIQUE INDEX idx_pages_unique_in_folder
ON pages(owner_user_id, folder_id, name)
WHERE folder_id IS NOT NULL
""")
    op.execute("""
CREATE UNIQUE INDEX idx_pages_unique_at_root
ON pages(owner_user_id, name)
WHERE folder_id IS NULL
""")
