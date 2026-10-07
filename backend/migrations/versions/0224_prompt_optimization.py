"""Continuous prompt optimization, immutable run evidence and business outcomes."""

from alembic import op

revision = "0224"
down_revision = "0223"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE rm_optimizations (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        reward_model_id uuid NOT NULL REFERENCES rm_reward_models(id),
        name text NOT NULL, agent text NOT NULL, scope text NOT NULL,
        metric jsonb NOT NULL,
        status text NOT NULL CHECK(status IN ('waiting_model','active','paused','completed','failed')),
        active_revision_id uuid,
        runs_per_arm integer NOT NULL CHECK(runs_per_arm BETWEEN 5 AND 500),
        max_rounds integer NOT NULL CHECK(max_rounds BETWEEN 1 AND 100),
        error text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE rm_prompt_revisions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        optimization_id uuid NOT NULL REFERENCES rm_optimizations(id) ON DELETE CASCADE,
        version integer NOT NULL, content text NOT NULL, rationale text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(optimization_id,version)
    )""")
    op.execute(
        "ALTER TABLE rm_optimizations ADD FOREIGN KEY(active_revision_id) REFERENCES rm_prompt_revisions(id) DEFERRABLE INITIALLY DEFERRED"
    )
    op.execute(
        "CREATE UNIQUE INDEX rm_optimization_active_scope ON rm_optimizations(owner_user_id,agent,scope) WHERE status IN ('waiting_model','active')"
    )
    op.execute("""CREATE TABLE rm_optimization_rounds (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        optimization_id uuid NOT NULL REFERENCES rm_optimizations(id) ON DELETE CASCADE,
        number integer NOT NULL,
        baseline_id uuid NOT NULL REFERENCES rm_prompt_revisions(id), agent_version text,
        candidate_id uuid REFERENCES rm_prompt_revisions(id),
        status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','generating','collecting','promoted','rejected','cancelled','failed')),
        proposal_input jsonb, report jsonb, error text,
        attempts integer NOT NULL DEFAULT 0, lease_token uuid, lease_until timestamptz,
        dispatched_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        UNIQUE(optimization_id,number)
    )""")
    op.execute(
        "CREATE UNIQUE INDEX rm_optimization_open_round ON rm_optimization_rounds(optimization_id) WHERE status IN ('queued','generating','collecting')"
    )
    op.execute("""CREATE TABLE rm_optimization_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        optimization_id uuid NOT NULL REFERENCES rm_optimizations(id) ON DELETE CASCADE,
        round_id uuid REFERENCES rm_optimization_rounds(id),
        revision_id uuid NOT NULL REFERENCES rm_prompt_revisions(id),
        work_key text NOT NULL, capture_external_id text NOT NULL, agent_version text NOT NULL,
        arm text NOT NULL CHECK(arm IN ('baseline','candidate','current')),
        status text NOT NULL DEFAULT 'assigned' CHECK(status IN ('assigned','queued','scoring','completed','failed','abandoned')),
        trace_id uuid REFERENCES rm_traces(id) ON DELETE SET NULL,
        trace_snapshot jsonb, evidence_hash text, submission_hash text,
        score_items jsonb, action_scores jsonb, reward double precision,
        outcome double precision, outcome_source text, outcome_at timestamptz,
        attempts integer NOT NULL DEFAULT 0, error text, lease_token uuid, lease_until timestamptz,
        dispatched_at timestamptz, assigned_at timestamptz NOT NULL DEFAULT now(), submitted_at timestamptz, finished_at timestamptz,
        UNIQUE(optimization_id,work_key)
    )""")
    op.execute(
        "CREATE INDEX rm_optimization_runs_trends ON rm_optimization_runs(optimization_id,assigned_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX rm_optimization_unique_evidence ON rm_optimization_runs(optimization_id,evidence_hash) WHERE evidence_hash IS NOT NULL"
    )
    op.execute("""CREATE TABLE rm_optimization_events (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        optimization_id uuid NOT NULL REFERENCES rm_optimizations(id) ON DELETE CASCADE,
        kind text NOT NULL, detail jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")


def downgrade():
    op.execute(
        "ALTER TABLE rm_optimizations DROP CONSTRAINT rm_optimizations_active_revision_id_fkey"
    )
    op.execute(
        "DROP TABLE rm_optimization_events,rm_optimization_runs,rm_optimization_rounds,rm_prompt_revisions,rm_optimizations"
    )
