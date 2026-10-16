"""Eval feedback: many signals per served prediction, and caller references.

Revision ID: 0239
Revises: 0236
"""

from alembic import op

revision = "0239"
down_revision = "0236"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE intuition_predictions ADD COLUMN ref text")
    op.execute(
        "ALTER TABLE intuition_predictions ADD COLUMN metadata jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "CREATE INDEX intuition_predictions_ref ON intuition_predictions(model_id, ref, created_at DESC) "
        "WHERE ref IS NOT NULL"
    )
    # A prediction collects feedback over time: a human correction now, a business
    # outcome days later, a downstream system's verdict. Rows are append-only.
    op.execute("""CREATE TABLE intuition_feedback (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        prediction_id uuid NOT NULL REFERENCES intuition_predictions(id) ON DELETE CASCADE,
        label text,
        value double precision,
        source text NOT NULL CHECK (source IN ('human', 'outcome', 'downstream')),
        note text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
        created_at timestamptz NOT NULL DEFAULT now(),
        CHECK (label IS NOT NULL OR value IS NOT NULL)
    )""")
    op.execute(
        "CREATE INDEX intuition_feedback_prediction ON intuition_feedback(prediction_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX intuition_feedback_model ON intuition_feedback(model_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE intuition_feedback")
    op.execute("DROP INDEX intuition_predictions_ref")
    op.execute("ALTER TABLE intuition_predictions DROP COLUMN metadata")
    op.execute("ALTER TABLE intuition_predictions DROP COLUMN ref")
