"""An eval can name another eval that grades its rubrics.

intuition_models.rubric_eval_id is an eval, owned by the same person, whose submissions are
rubrics: its examples are rubrics labeled good or bad, and its own rubric says what makes a
rubric a good one to grade with. When a rubric change is proposed on an eval that names one,
the rubric in use and the proposed rubric are both scored with it (rubric_quality.py).

Revision ID: 0261
Revises: 0260
"""

from alembic import op

revision = "0261"
down_revision = "0260"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE intuition_models ADD COLUMN rubric_eval_id uuid "
        "REFERENCES intuition_models(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE intuition_models DROP COLUMN rubric_eval_id")
