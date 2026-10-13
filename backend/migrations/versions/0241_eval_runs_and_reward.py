"""Eval runs (trajectory outcomes) and evals as the reward for prompt optimization.

Revision ID: 0241
Revises: 0240
"""

from alembic import op

revision = "0241"
down_revision = "0240"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A run groups the eval calls made while one task was carried out (an agent
    # episode, a support conversation). Its outcome arrives once, later, and is
    # credited back to the decisions inside it.
    op.execute("""CREATE TABLE intuition_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        external_id text NOT NULL CHECK (length(external_id) BETWEEN 1 AND 200),
        outcome double precision CHECK (outcome BETWEEN 0 AND 1),
        outcome_source text,
        note text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
        metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        outcome_at timestamptz,
        UNIQUE (owner_user_id, external_id)
    )""")
    op.execute(
        "ALTER TABLE intuition_predictions ADD COLUMN run_id uuid "
        "REFERENCES intuition_runs(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE intuition_predictions ADD COLUMN step integer")
    op.execute(
        "CREATE INDEX intuition_predictions_run ON intuition_predictions(run_id) WHERE run_id IS NOT NULL"
    )

    # Prompt optimization can be scored by an eval instead of a GPU reward model.
    # The eval version is pinned when the program starts so the judge never
    # changes mid-comparison.
    op.execute("ALTER TABLE rm_optimizations ALTER COLUMN reward_model_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE rm_optimizations ADD COLUMN intuition_model_id uuid REFERENCES intuition_models(id)"
    )
    op.execute(
        "ALTER TABLE rm_optimizations ADD COLUMN intuition_version_id uuid REFERENCES intuition_versions(id)"
    )
    op.execute("ALTER TABLE rm_optimizations ADD COLUMN target_label text")
    op.execute(
        """ALTER TABLE rm_optimizations ADD CONSTRAINT rm_optimizations_one_scorer CHECK (
            (reward_model_id IS NOT NULL AND intuition_model_id IS NULL)
            OR (reward_model_id IS NULL AND intuition_model_id IS NOT NULL
                AND intuition_version_id IS NOT NULL AND target_label IS NOT NULL))"""
    )


def downgrade() -> None:
    op.execute("ALTER TABLE rm_optimizations DROP CONSTRAINT rm_optimizations_one_scorer")
    op.execute("DELETE FROM rm_optimizations WHERE reward_model_id IS NULL")
    op.execute("ALTER TABLE rm_optimizations DROP COLUMN target_label")
    op.execute("ALTER TABLE rm_optimizations DROP COLUMN intuition_version_id")
    op.execute("ALTER TABLE rm_optimizations DROP COLUMN intuition_model_id")
    op.execute("ALTER TABLE rm_optimizations ALTER COLUMN reward_model_id SET NOT NULL")
    op.execute("DROP INDEX intuition_predictions_run")
    op.execute("ALTER TABLE intuition_predictions DROP COLUMN step")
    op.execute("ALTER TABLE intuition_predictions DROP COLUMN run_id")
    op.execute("DROP TABLE intuition_runs")
