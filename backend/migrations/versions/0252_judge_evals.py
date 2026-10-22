"""Evals scored by a judge: examples in (good or bad), score plus explanation out.

An intuition model with scorer 'judge' is scored by Claude grading the agent's output
1-5 on each trait of the eval, side by side with the eval's good and bad examples
(services/evals). Models with scorer 'fitted' keep the rubric-and-fitted-head path.
traits is written by the build; build holds its progress and agreement metrics;
instructions is the person's optional one-line description of what to judge.
Judge evals have no versions, so their logged calls have no version_id.

Revision ID: 0252
Revises: 0251
"""

from alembic import op

revision = "0252"
down_revision = "0251"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE intuition_models "
        "ADD COLUMN scorer text NOT NULL DEFAULT 'fitted' CHECK (scorer IN ('fitted', 'judge')), "
        "ADD COLUMN instructions text NOT NULL DEFAULT '', "
        "ADD COLUMN traits jsonb, "
        "ADD COLUMN build jsonb"
    )
    op.execute("ALTER TABLE intuition_predictions ALTER COLUMN version_id DROP NOT NULL")


def downgrade() -> None:
    op.execute("DELETE FROM intuition_predictions WHERE version_id IS NULL")
    op.execute("ALTER TABLE intuition_predictions ALTER COLUMN version_id SET NOT NULL")
    op.execute(
        "ALTER TABLE intuition_models "
        "DROP COLUMN build, DROP COLUMN traits, DROP COLUMN instructions, DROP COLUMN scorer"
    )
