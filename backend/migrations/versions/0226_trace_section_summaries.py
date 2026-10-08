"""Cache generated trace section copy independently of scores and source events."""

from alembic import op

revision = "0226"
down_revision = "0225"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE rm_trace_section_summaries (
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        content_key text NOT NULL,
        copy jsonb,
        retry_after timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(trace_id, content_key)
    )""")


def downgrade():
    op.execute("DROP TABLE rm_trace_section_summaries")
