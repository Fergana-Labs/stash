"""Persist an operator-selected product checkpoint per account."""

from alembic import op

revision = "0222"
down_revision = "0221"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE users ADD COLUMN product_checkpoint text NOT NULL DEFAULT 'latest'
        CHECK (product_checkpoint IN ('latest', 'floodgate-2026-10-05'))""")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN product_checkpoint")
