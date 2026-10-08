"""Store step labels and rule-based step scores per trace."""

from alembic import op

revision = "0225"
down_revision = "0224"
branch_labels = None
depends_on = None


def upgrade():
    # One row per trace, replaced when the trace's steps change. `chunks` holds
    # a hash per labeled chunk so an appended trace relabels only what is new.
    # Kept out of rm_traces and rm_trace_steps so annotation never fires their
    # change triggers.
    op.execute("""
        CREATE TABLE rm_step_labels (
            trace_id       uuid PRIMARY KEY REFERENCES rm_traces(id) ON DELETE CASCADE,
            owner_user_id  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            fingerprint    text NOT NULL,
            labels         jsonb NOT NULL,
            rewards        jsonb NOT NULL,
            summary        jsonb,
            chunks         jsonb NOT NULL,
            label_model    text NOT NULL,
            labeled_at     timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX rm_step_labels_owner ON rm_step_labels (owner_user_id)")


def downgrade():
    op.execute("DROP TABLE rm_step_labels")
