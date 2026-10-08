"""Private inline images attached to immutable trace steps."""

from alembic import op

revision = "0225"
down_revision = "0224"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE rm_trace_images (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        step_id uuid NOT NULL REFERENCES rm_trace_steps(id) ON DELETE CASCADE,
        position integer NOT NULL,
        source_start integer NOT NULL CHECK(source_start >= 0),
        source_end integer NOT NULL CHECK(source_end > source_start),
        content_type text NOT NULL,
        width integer NOT NULL, height integer NOT NULL,
        storage_key text NOT NULL,
        UNIQUE(step_id, position)
    )""")


def downgrade():
    op.execute("DROP TABLE rm_trace_images")
