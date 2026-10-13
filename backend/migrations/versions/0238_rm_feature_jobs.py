"""Durable private feature extraction and head-specific scoring results."""

from alembic import op

revision = "0238"
down_revision = "0237"
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
    # Keep the default table and its two-column conflict target intact. An old
    # API or worker can remain live during this additive migration without
    # seeing private jobs or losing its original unique-index inference.
    op.execute("""CREATE TABLE rm_customer_scoring_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        reward_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
        customer_head_id uuid NOT NULL REFERENCES rm_customer_heads(id) ON DELETE CASCADE,
        trace_updated_at timestamptz NOT NULL,
        model_finished_at timestamptz NOT NULL,
        status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed')),
        error text,
        progress jsonb,
        customer_scores jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        dispatched_at timestamptz,
        finished_at timestamptz
    )""")
    op.execute("""CREATE UNIQUE INDEX rm_customer_scoring_runs_active ON rm_customer_scoring_runs
        (trace_id,reward_model_id,customer_head_id)
        WHERE status IN ('queued','running')""")
    op.execute(
        "CREATE INDEX rm_customer_scoring_runs_queue ON rm_customer_scoring_runs(status,created_at)"
    )
    op.execute(
        "CREATE INDEX rm_customer_scoring_runs_trace ON rm_customer_scoring_runs(trace_id,created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE rm_customer_scoring_runs")
    op.execute("DROP TABLE rm_customer_feature_jobs")
