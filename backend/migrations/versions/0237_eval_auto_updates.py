"""Durable debounce and progress for automatic eval calibration."""

from alembic import op

revision = "0237"
down_revision = "0236"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE intuition_updates (
        model_id uuid PRIMARY KEY REFERENCES intuition_models(id) ON DELETE CASCADE,
        revision bigint NOT NULL DEFAULT 1,
        completed_revision bigint NOT NULL DEFAULT 0,
        rubric_dirty boolean NOT NULL DEFAULT true,
        state text NOT NULL DEFAULT 'pending'
            CHECK (state IN ('pending','queued','running','idle','needs_examples','failed')),
        run_after timestamptz NOT NULL DEFAULT now() + interval '1 minute',
        started_at timestamptz,
        finished_at timestamptz,
        stage text,
        error text,
        attempts integer NOT NULL DEFAULT 0
    )""")
    op.execute(
        "CREATE INDEX intuition_updates_due ON intuition_updates(run_after) WHERE state IN ('pending','queued','running')"
    )


def downgrade():
    op.execute("DROP TABLE intuition_updates")
