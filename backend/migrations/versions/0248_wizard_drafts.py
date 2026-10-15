"""Keep unsent wizard input with resumable eval drafts.

Revision ID: 0248
Revises: 0247
"""

from alembic import op

revision = "0248"
down_revision = "0247"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE intuition_wizard_sessions ADD COLUMN draft_input text NOT NULL DEFAULT ''"
    )


def downgrade() -> None:
    op.drop_column("intuition_wizard_sessions", "draft_input")
