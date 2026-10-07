"""Inspectable prompt graders, automatic assessments, feedback and changes.

Revision ID: 0217
Revises: 0216
"""

from alembic import op

revision = "0217"
down_revision = "0216"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE rm_wb_graders (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name text NOT NULL, scope jsonb NOT NULL DEFAULT '{}',
        enabled boolean NOT NULL DEFAULT true, active_version_id uuid,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )
    """)
    op.execute("""
        CREATE TABLE rm_wb_grader_versions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        grader_id uuid NOT NULL REFERENCES rm_wb_graders(id) ON DELETE CASCADE,
        version integer NOT NULL, config jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(grader_id, version)
    )
    """)
    op.execute("""
        ALTER TABLE rm_wb_graders ADD CONSTRAINT rm_wb_active_version_fk
        FOREIGN KEY (active_version_id) REFERENCES rm_wb_grader_versions(id)
    """)
    op.execute("""
        CREATE TABLE rm_wb_assessments (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        target_step_id uuid REFERENCES rm_trace_steps(id) ON DELETE SET NULL,
        target_index integer NOT NULL, grader_id uuid NOT NULL REFERENCES rm_wb_graders(id) ON DELETE CASCADE,
        grader_version_id uuid NOT NULL REFERENCES rm_wb_grader_versions(id),
        criterion_id text NOT NULL, criterion_name text NOT NULL,
        input_hash text NOT NULL, input_snapshot jsonb NOT NULL, attempt integer NOT NULL DEFAULT 1,
        status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed')),
        verdict text CHECK(verdict IN ('meets','violates','insufficient_evidence','not_applicable')),
        reason text, evidence_step_ids jsonb NOT NULL DEFAULT '[]', raw_output jsonb,
        confidence double precision, probabilities jsonb, usage jsonb, duration_ms integer, error text,
        created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, finished_at timestamptz,
        UNIQUE(trace_id, grader_version_id, input_hash, criterion_id, attempt)
    )
    """)
    op.execute("""
        CREATE INDEX rm_wb_assessments_trace ON rm_wb_assessments(trace_id, created_at)
    """)
    op.execute("""
        CREATE INDEX rm_wb_assessments_owner ON rm_wb_assessments(owner_user_id, created_at)
    """)
    op.execute("""
        CREATE TABLE rm_wb_feedback (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        author_user_id uuid NOT NULL REFERENCES users(id),
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        assessment_id uuid REFERENCES rm_wb_assessments(id) ON DELETE SET NULL,
        target_step_id uuid REFERENCES rm_trace_steps(id) ON DELETE SET NULL,
        comment text NOT NULL, proposed_verdict text CHECK(proposed_verdict IN ('meets','violates','insufficient_evidence','not_applicable')),
        change_kind text NOT NULL DEFAULT 'unclear' CHECK(change_kind IN ('judge_error','agent_error','both','requirement_change','unclear')),
        source text NOT NULL DEFAULT 'human_comment' CHECK(source IN ('human_comment','trace_extraction')),
        review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','accepted','rejected')),
        reviewed_by uuid REFERENCES users(id), reviewed_at timestamptz,
        status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed')),
        interpretation jsonb, error text, source_event_id uuid, created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(trace_id, source_event_id)
    )
    """)
    op.execute("""
        CREATE TABLE rm_wb_changes (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        grader_id uuid NOT NULL REFERENCES rm_wb_graders(id) ON DELETE CASCADE,
        feedback_id uuid REFERENCES rm_wb_feedback(id) ON DELETE SET NULL,
        kind text NOT NULL CHECK(kind IN ('grader','instruction')),
        status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','checking','checked','released','rejected','failed')),
        title text NOT NULL, content jsonb NOT NULL, parent_version_id uuid, version_id uuid REFERENCES rm_wb_grader_versions(id),
        check_report jsonb, error text, created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(), released_at timestamptz
    )
    """)
    op.execute("""
        CREATE TABLE rm_wb_history (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        record_type text NOT NULL, record_id uuid NOT NULL, actor_user_id uuid REFERENCES users(id),
        action text NOT NULL, snapshot jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )
    """)
    op.execute("""
        CREATE TABLE rm_wb_queue (
        trace_id uuid PRIMARY KEY REFERENCES rm_traces(id) ON DELETE CASCADE,
        due_at timestamptz NOT NULL DEFAULT now(), status text NOT NULL DEFAULT 'queued',
        attempts integer NOT NULL DEFAULT 0, error text, started_at timestamptz,
        requested_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz
    )
    """)
    op.execute("""
        CREATE INDEX rm_wb_queue_due ON rm_wb_queue(due_at) WHERE status='queued'
    """)
    op.execute("""
        CREATE TABLE rm_wb_trace_reviewers (
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(trace_id,user_id)
    )
    """)
    op.execute("""
        CREATE FUNCTION rm_wb_trace_changed() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP='INSERT' OR NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
            INSERT INTO rm_wb_queue(trace_id,due_at) VALUES(NEW.id, now()+interval '15 seconds')
            ON CONFLICT(trace_id) DO UPDATE SET due_at=EXCLUDED.due_at,requested_at=now(),
                status=CASE WHEN rm_wb_queue.status='running' THEN 'running' ELSE 'queued' END,
                attempts=0,error=NULL;
        END IF;
        RETURN NEW;
    END $$
    """)
    op.execute("""
        CREATE TRIGGER rm_wb_trace_changed AFTER INSERT OR UPDATE OF updated_at ON rm_traces
        FOR EACH ROW EXECUTE FUNCTION rm_wb_trace_changed()
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER rm_wb_trace_changed ON rm_traces
    """)
    op.execute("""
        DROP FUNCTION rm_wb_trace_changed()
    """)
    op.execute("""
        DROP TABLE rm_wb_trace_reviewers,rm_wb_queue,rm_wb_history,rm_wb_changes,rm_wb_feedback,rm_wb_assessments
    """)
    op.execute("""
        ALTER TABLE rm_wb_graders DROP CONSTRAINT rm_wb_active_version_fk
    """)
    op.execute("""
        DROP TABLE rm_wb_grader_versions,rm_wb_graders
    """)
