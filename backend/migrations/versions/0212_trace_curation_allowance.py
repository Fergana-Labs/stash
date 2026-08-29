"""Replace monthly curator-run credits with a lifetime trace allowance."""

from alembic import op

revision = "0212"
down_revision = "0211"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agents DROP COLUMN month_run_count")
    op.execute("ALTER TABLE agents DROP COLUMN month_run_anchor")


def downgrade() -> None:
    op.execute("ALTER TABLE agents ADD COLUMN month_run_count integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE agents ADD COLUMN month_run_anchor date")
