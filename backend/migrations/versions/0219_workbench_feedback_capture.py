"""Durable, bounded scans for explicit corrections in captured user messages.

Revision ID: 0219
Revises: 0218
"""

from alembic import op

revision = "0219"
down_revision = "0218"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE rm_wb_feedback_scans (
            source_event_id uuid PRIMARY KEY REFERENCES rm_trace_steps(id) ON DELETE CASCADE,
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
            source_index integer NOT NULL,
            status text NOT NULL CHECK (status IN ('skipped','running','completed','failed')),
            attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
            claim_id uuid, input_snapshot jsonb NOT NULL, model text,
            raw_output jsonb, feedback_id uuid REFERENCES rm_wb_feedback(id) ON DELETE SET NULL,
            error text, created_at timestamptz NOT NULL DEFAULT now(),
            last_attempt_at timestamptz, due_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz
        )
    """)
    op.execute("""
        CREATE INDEX rm_wb_feedback_scans_owner_attempt
            ON rm_wb_feedback_scans(owner_user_id,last_attempt_at)
    """)
    op.execute("CREATE INDEX rm_wb_feedback_scans_trace ON rm_wb_feedback_scans(trace_id)")


def downgrade() -> None:
    op.execute("DROP TABLE rm_wb_feedback_scans")
