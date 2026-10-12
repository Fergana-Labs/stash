"""Durable, bounded batches for eager personal-model scoring."""

from alembic import op

revision = "0236"
down_revision = "0235"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE rm_scoring_batches (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        reward_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
        status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed')),
        remote_call_id text,
        error text,
        created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        finished_at timestamptz
    )""")
    op.execute("""ALTER TABLE rm_scoring_runs ADD COLUMN batch_id uuid
        REFERENCES rm_scoring_batches(id) ON DELETE SET NULL""")
    op.execute("ALTER TABLE rm_scoring_runs ADD COLUMN model_finished_at timestamptz")
    op.execute("ALTER TABLE rm_scoring_runs ADD COLUMN requested_at timestamptz")
    op.execute("""UPDATE rm_scoring_runs r SET model_finished_at=m.finished_at
        FROM rm_reward_models m WHERE r.reward_model_id=m.id AND m.status='succeeded'
        AND r.created_at>=m.finished_at""")
    op.execute(
        "CREATE INDEX rm_scoring_runs_batch ON rm_scoring_runs(batch_id) WHERE batch_id IS NOT NULL"
    )
    op.execute("""CREATE INDEX rm_scoring_runs_cache ON rm_scoring_runs
        (reward_model_id,trace_id,trace_updated_at,model_finished_at) WHERE status='succeeded'""")
    op.execute("""CREATE UNIQUE INDEX rm_scoring_batches_active ON rm_scoring_batches(reward_model_id)
        WHERE status IN ('queued','running')""")


def downgrade():
    op.execute("DROP INDEX rm_scoring_runs_cache")
    op.execute(
        "ALTER TABLE rm_scoring_runs DROP COLUMN batch_id, DROP COLUMN model_finished_at, DROP COLUMN requested_at"
    )
    op.execute("DROP TABLE rm_scoring_batches")
