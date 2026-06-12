"""GitHub attribution for imported skills.

Revision ID: 0111
Revises: 0110
"""

from alembic import op

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE skills ADD COLUMN source_github_url VARCHAR(512)")
    op.execute(
        "CREATE UNIQUE INDEX idx_skills_source_github_url ON skills (source_github_url) "
        "WHERE source_github_url IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE skills DROP COLUMN source_github_url")
