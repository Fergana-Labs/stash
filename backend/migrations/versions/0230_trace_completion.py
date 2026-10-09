"""Cache estimated task completion independently of reward scores."""

from alembic import op

revision = "0230"
down_revision = "0229"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE rm_trace_completion (
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        content_key text NOT NULL,
        estimate jsonb,
        retry_after timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(trace_id, content_key)
    )""")


def downgrade():
    op.execute("DROP TABLE rm_trace_completion")
