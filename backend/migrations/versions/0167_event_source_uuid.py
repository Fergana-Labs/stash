"""Give every history_events row a producer-assigned idempotency key.

history_events had no uniqueness beyond its random PK, so the same event
could land twice: a hook's 2s timeout fired while the backend commit was
still in flight (the queued body replayed later), concurrent transcript
uploads raced the count-then-insert guard, and re-imports re-inserted every
line. source_uuid + a unique index makes every one of those a no-op at the
database instead of a duplicate row.

Existing rows are backfilled with random ids — pre-existing duplicates are
left as-is (deliberate: content-based cleanup risks collapsing genuinely
repeated messages); idempotency applies going forward.

NULLS NOT DISTINCT keeps the index enforced for personal events, whose
owner_user_id is NULL.
"""

from alembic import op

revision = "0167"
down_revision = "0166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE history_events ADD COLUMN source_uuid TEXT")
    op.execute(
        "UPDATE history_events SET source_uuid = gen_random_uuid()::text WHERE source_uuid IS NULL"
    )
    op.execute("ALTER TABLE history_events ALTER COLUMN source_uuid SET NOT NULL")
    op.execute(
        "CREATE UNIQUE INDEX uq_history_events_source "
        "ON history_events (owner_user_id, session_id, source_uuid) NULLS NOT DISTINCT"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_history_events_source")
    op.execute("ALTER TABLE history_events DROP COLUMN source_uuid")
