"""Sessions carry their own last_event_at.

The sessions list used to aggregate MAX(created_at) over every accessible
history_events row (1M+ in prod) on every page load just to order sessions by
recency — an empty page paid for the user's whole event history. Recency is
now a column on the session row, maintained at ingest, so the list selects a
page of sessions first and only touches the events of that page.

Revision ID: 0199
Revises: 0198
"""

from alembic import op

revision = "0199"
down_revision = "0198"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN last_event_at timestamptz")
    op.execute(
        """
        UPDATE sessions s SET last_event_at = agg.max_created
        FROM (SELECT owner_user_id, session_id, MAX(created_at) AS max_created
              FROM history_events WHERE session_id IS NOT NULL
              GROUP BY owner_user_id, session_id) agg
        WHERE agg.owner_user_id = s.owner_user_id AND agg.session_id = s.session_id
        """
    )
    # Sessions that never got an event are as recent as their start.
    op.execute("UPDATE sessions SET last_event_at = started_at WHERE last_event_at IS NULL")
    op.execute("ALTER TABLE sessions ALTER COLUMN last_event_at SET NOT NULL")
    op.execute(
        "CREATE INDEX idx_sessions_owner_last_event "
        "ON sessions(owner_user_id, last_event_at DESC) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sessions_owner_last_event")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS last_event_at")
