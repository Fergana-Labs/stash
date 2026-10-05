"""Learned per-action rewards and asynchronous inference jobs.

Revision ID: 0214
Revises: 0213
"""

from alembic import op

revision = "0214"
down_revision = "0213"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE rm_action_scores (
            reward_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
            step_id uuid NOT NULL REFERENCES rm_trace_steps(id) ON DELETE CASCADE,
            score double precision NOT NULL CHECK (score > '-Infinity'::float8 AND score < 'Infinity'::float8),
            credit double precision NOT NULL CHECK (credit BETWEEN -1 AND 1),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (reward_model_id, step_id)
        )
    """)
    op.execute("CREATE INDEX rm_action_scores_step ON rm_action_scores (step_id)")
    op.execute("""
        CREATE TABLE rm_scoring_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
            reward_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
            status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            finished_at timestamptz
        )
    """)
    op.execute("CREATE INDEX rm_scoring_runs_trace ON rm_scoring_runs (trace_id, created_at DESC)")
    op.execute("""CREATE UNIQUE INDEX rm_scoring_runs_active
        ON rm_scoring_runs (trace_id, reward_model_id) WHERE status IN ('queued', 'running')""")


def downgrade() -> None:
    op.execute("DROP TABLE rm_scoring_runs")
    op.execute("DROP TABLE rm_action_scores")
