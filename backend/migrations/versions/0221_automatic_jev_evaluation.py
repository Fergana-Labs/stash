"""Built-in trace outcome and retrospective action credit, without grader setup."""

from alembic import op

revision = "0221"
down_revision = "0220"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE rm_wb_graders ADD COLUMN builtin boolean NOT NULL DEFAULT false")
    op.execute(
        "CREATE UNIQUE INDEX rm_wb_builtin_scope ON rm_wb_graders(owner_user_id,scope) WHERE builtin"
    )
    op.execute("""CREATE TABLE rm_wb_evaluations (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        revision_hash text NOT NULL, policy_version text NOT NULL, model text NOT NULL, trace_updated_at timestamptz NOT NULL,
        boundary jsonb NOT NULL, trace_snapshot jsonb NOT NULL,
        status text NOT NULL DEFAULT 'running' CHECK(status IN ('running','completed','failed')),
        outcome text CHECK(outcome IN ('success','partial_success','failure','insufficient_evidence')),
        outcome_confidence double precision, outcome_probabilities jsonb,
        total_actions integer NOT NULL, credited_actions integer NOT NULL DEFAULT 0,
        error text, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        UNIQUE(trace_id,revision_hash,policy_version,model)
    )""")
    op.execute(
        "CREATE INDEX rm_wb_evaluations_trace ON rm_wb_evaluations(trace_id,created_at DESC)"
    )
    op.execute("""CREATE TABLE rm_wb_evaluation_calls (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        evaluation_id uuid NOT NULL REFERENCES rm_wb_evaluations(id) ON DELETE CASCADE,
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        batch_index integer NOT NULL, attempt integer NOT NULL,
        input_snapshot jsonb NOT NULL, raw_output jsonb, result jsonb,
        status text NOT NULL CHECK(status IN ('running','completed','failed')),
        error text, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        UNIQUE(evaluation_id,batch_index,attempt)
    )""")
    op.execute(
        "CREATE INDEX rm_wb_evaluation_calls_budget ON rm_wb_evaluation_calls(owner_user_id,created_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX rm_wb_evaluation_batch_completed ON rm_wb_evaluation_calls(evaluation_id,batch_index) WHERE status='completed'"
    )
    op.execute("ALTER TABLE rm_wb_feedback ADD COLUMN evaluation_target_step_id uuid")
    op.execute(
        "ALTER TABLE rm_wb_feedback ADD COLUMN evaluation_id uuid REFERENCES rm_wb_evaluations(id) ON DELETE SET NULL"
    )
    # Ingestion already queues every changed trace. Bootstrap existing captured
    # records only for accounts with reward-model access; no grader creation.
    op.execute("""INSERT INTO rm_wb_queue(trace_id)
        SELECT t.id FROM rm_traces t JOIN users u ON u.id=t.owner_user_id WHERE u.reward_models_enabled
        ON CONFLICT(trace_id) DO UPDATE SET
        status=CASE WHEN rm_wb_queue.status='running' THEN 'running' ELSE 'queued' END,
        due_at=now(),requested_at=now(),
        attempts=CASE WHEN rm_wb_queue.status='running' THEN rm_wb_queue.attempts ELSE 0 END,error=NULL""")


def downgrade():
    op.execute(
        "ALTER TABLE rm_wb_feedback DROP COLUMN evaluation_id, DROP COLUMN evaluation_target_step_id"
    )
    op.execute("DROP TABLE rm_wb_evaluation_calls,rm_wb_evaluations")
    op.execute("DROP INDEX rm_wb_builtin_scope")
    op.execute("ALTER TABLE rm_wb_graders DROP COLUMN builtin")
