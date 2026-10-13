"""Durable private feature extraction and head-specific scoring results."""

from alembic import op

revision = "0237"
down_revision = "0236"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE rm_customer_feature_jobs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        shared_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
        trace_id uuid REFERENCES rm_traces(id) ON DELETE CASCADE,
        trace_updated_at timestamptz,
        request_hash text NOT NULL,
        feature_version text NOT NULL,
        manifest_digest text NOT NULL,
        inputs jsonb NOT NULL,
        status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed')),
        attempts integer NOT NULL DEFAULT 0,
        error text,
        pair_id uuid REFERENCES rm_customer_feature_pairs(id) ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        dispatched_at timestamptz,
        finished_at timestamptz,
        CHECK ((trace_id IS NULL) = (trace_updated_at IS NULL)),
        UNIQUE(owner_user_id,shared_model_id,request_hash)
    )""")
    op.execute(
        "CREATE INDEX rm_customer_feature_jobs_queue ON rm_customer_feature_jobs(status,created_at)"
    )
    op.execute("""ALTER TABLE rm_scoring_runs
        ADD COLUMN customer_head_id uuid REFERENCES rm_customer_heads(id) ON DELETE CASCADE,
        ADD COLUMN customer_scores jsonb""")
    op.execute("DROP INDEX rm_scoring_runs_active")
    op.execute("""CREATE UNIQUE INDEX rm_scoring_runs_active ON rm_scoring_runs
        (trace_id,reward_model_id,(coalesce(customer_head_id,'00000000-0000-0000-0000-000000000000'::uuid)))
        WHERE status IN ('queued','running')""")


def downgrade():
    op.execute("DROP TABLE rm_customer_feature_jobs")
    # The old schema cannot represent personalized runs without colliding with defaults.
    op.execute("DELETE FROM rm_scoring_runs WHERE customer_head_id IS NOT NULL")
    op.execute("DROP INDEX rm_scoring_runs_active")
    op.execute(
        "ALTER TABLE rm_scoring_runs DROP COLUMN customer_head_id,DROP COLUMN customer_scores"
    )
    op.execute("""CREATE UNIQUE INDEX rm_scoring_runs_active ON rm_scoring_runs
        (trace_id,reward_model_id) WHERE status IN ('queued','running')""")
