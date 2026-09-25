"""Start new accounts in Skills while preserving existing product access."""

from alembic import op

revision = "0221"
down_revision = "0220"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN developer_platform_only SET DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN developer_platform_only SET DEFAULT true")
