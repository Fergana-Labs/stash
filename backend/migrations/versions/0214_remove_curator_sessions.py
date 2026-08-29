"""Remove internal curator jobs from user-visible sessions."""

from alembic import op

revision = "0214"
down_revision = "0213"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM sessions WHERE session_id LIKE 'agent-curate-%'")


def downgrade() -> None:
    pass
