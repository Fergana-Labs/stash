"""Record where an event sat in the upload that wrote it.

push_events_batch stamps every event that arrives without its own created_at
with the same instant, and transcript reads order by (created_at, id) where id
is a random UUID — so a question and the answer to it, uploaded together, came
back in either order. About half the time the transcript showed the answer
above the question. seq holds the event's position in the array the caller
sent, and the reads break ties on it.

Every caller of push_events_batch fills it in, so this covers the other way a
transcript ends up with tied timestamps: a JSONL file whose own events share
one. Those now order by position in the file rather than by id. The
single-event endpoint leaves seq NULL and needs nothing — each call stamps its
own now().

Existing rows stay NULL, as do rows written one at a time. The order a stored
batch was written in was never recorded, so it cannot be recovered, and
backfilling would rewrite a multi-gigabyte table while the backend waits on it
at boot (migrations run at startup). NULLs sort last and tie among themselves,
falling through to id — exactly what those rows do today.

Revision ID: 0189
Revises: 0188
"""

from alembic import op

revision = "0189"
down_revision = "0188"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No default, so this is catalog-only: Postgres rewrites the whole table
    # for a column added with a volatile default, and this table is large.
    op.execute("ALTER TABLE history_events ADD COLUMN seq INT")


def downgrade() -> None:
    op.execute("ALTER TABLE history_events DROP COLUMN seq")
