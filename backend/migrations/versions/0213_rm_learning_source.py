"""Identify existing extracted feedback as user feedback, distinct from AI judgments."""

from alembic import op

revision = "0213"
down_revision = "0212"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE rm_reward_models m SET feedback = (
            SELECT jsonb_agg(item || '{"source":"user_feedback"}'::jsonb ORDER BY ord)
            FROM jsonb_array_elements(m.feedback) WITH ORDINALITY AS f(item, ord)
        ) WHERE jsonb_array_length(feedback) > 0
    """)
    op.execute("""
        UPDATE rm_reward_models m SET training_pairs = (
            SELECT jsonb_agg(
                CASE WHEN item->>'source' = 'feedback_revision'
                THEN jsonb_set(item, '{evidence,source}', '"user_feedback"'::jsonb)
                ELSE item END ORDER BY ord
            ) FROM jsonb_array_elements(m.training_pairs) WITH ORDINALITY AS p(item, ord)
        ) WHERE jsonb_array_length(training_pairs) > 0
    """)


def downgrade() -> None:
    raise RuntimeError("Learning provenance cannot be removed without misattributing AI judgments")
