"""Record when a folder became a Skill.

Revision ID: 0208
Revises: 0207
"""

from alembic import op

revision = "0208"
down_revision = "0207"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE folders ADD COLUMN skill_created_at timestamptz")
    op.execute("UPDATE folders SET skill_created_at = created_at WHERE is_skill")
    op.execute(
        "CREATE INDEX idx_folders_skill_created_at "
        "ON folders(owner_user_id, skill_created_at DESC) WHERE is_skill"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_folders_skill_created_at")
    op.execute("ALTER TABLE folders DROP COLUMN skill_created_at")
