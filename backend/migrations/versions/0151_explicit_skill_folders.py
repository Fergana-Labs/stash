"""Store skill identity on folders instead of deriving it from SKILL.md.

Revision ID: 0151
Revises: 0150
"""

from alembic import op

revision = "0151"
down_revision = "0150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE folders ADD COLUMN is_skill boolean NOT NULL DEFAULT false")
    op.execute(
        "UPDATE folders f SET is_skill = true "
        "WHERE EXISTS (SELECT 1 FROM pages p WHERE p.folder_id = f.id "
        "AND p.name = 'SKILL.md' AND p.deleted_at IS NULL)"
    )
    op.execute("CREATE INDEX idx_folders_skills ON folders (owner_user_id) WHERE is_skill")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_folders_skills")
    op.execute("ALTER TABLE folders DROP COLUMN IF EXISTS is_skill")
