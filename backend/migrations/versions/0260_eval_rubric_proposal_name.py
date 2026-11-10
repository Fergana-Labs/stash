"""A proposed rubric change can carry a name, as a branch has one.

eval_rubric_proposals.name is what the change is called next to the rubric it merges into
("no-claudeslop-indicators"). Empty means the page names it after its first edit.

Revision ID: 0260
Revises: 0259
"""

from alembic import op

revision = "0260"
down_revision = "0259"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE eval_rubric_proposals ADD COLUMN name text NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE eval_rubric_proposals DROP COLUMN name")
