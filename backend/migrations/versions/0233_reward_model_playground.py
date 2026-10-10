"""Private saved-checkpoint playground runs.

Revision ID: 0233
Revises: 0232
"""

from alembic import op

revision = "0233"
down_revision = "0232"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE rm_playground_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        reward_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
        status text NOT NULL DEFAULT 'queued'
            CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
        input jsonb NOT NULL,
        scores jsonb,
        error text,
        created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        finished_at timestamptz
    )""")
    op.execute(
        "CREATE INDEX ON rm_playground_runs (owner_user_id, reward_model_id, created_at DESC)"
    )
    op.execute("""CREATE UNIQUE INDEX rm_playground_one_active_per_owner
        ON rm_playground_runs (owner_user_id) WHERE status IN ('queued', 'running')""")


def downgrade() -> None:
    op.execute("DROP TABLE rm_playground_runs")
