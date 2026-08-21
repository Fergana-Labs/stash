"""Record the order events were written in, so a batch reads back in order.

push_events_batch stamps every event in one upload with the same created_at,
and transcript reads order by (created_at, id) where id is a random UUID — so
a question and the answer to it, uploaded together, came back in either order.
About half the time the transcript showed the answer above the question. seq is
a monotonic counter that breaks those ties by insertion order.

Existing rows are deliberately left NULL. The order they were inserted in was
never stored, so it cannot be recovered, and backfilling would rewrite a
multi-gigabyte table while the backend waits on it at boot (migrations run at
startup). NULLs sort last and tie among themselves, falling through to id —
exactly what those rows do today.

Revision ID: 0189
Revises: 0188
"""

from alembic import op

revision = "0189"
down_revision = "0188"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Three statements rather than one ADD COLUMN ... DEFAULT nextval(...):
    # nextval is volatile, and Postgres rewrites the entire table for a column
    # added with a volatile default. Adding the column bare and attaching the
    # default afterwards is catalog-only, so this is instant on a large table.
    op.execute("ALTER TABLE history_events ADD COLUMN seq BIGINT")
    op.execute("CREATE SEQUENCE history_events_seq_seq OWNED BY history_events.seq")
    op.execute(
        "ALTER TABLE history_events ALTER COLUMN seq SET DEFAULT nextval('history_events_seq_seq')"
    )


def downgrade() -> None:
    # The sequence is OWNED BY the column, so dropping the column drops it too.
    op.execute("ALTER TABLE history_events DROP COLUMN seq")
