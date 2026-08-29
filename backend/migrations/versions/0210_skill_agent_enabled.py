"""Let users choose which Skills are provided to agents.

Revision ID: 0210
Revises: 0209
"""

from alembic import op

revision = "0210"
down_revision = "0209"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE folders ADD COLUMN agent_enabled BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute("ALTER TABLE drive_documents ADD COLUMN agent_enabled BOOLEAN NOT NULL DEFAULT TRUE")


def downgrade() -> None:
    op.execute("ALTER TABLE drive_documents DROP COLUMN agent_enabled")
    op.execute("ALTER TABLE folders DROP COLUMN agent_enabled")
