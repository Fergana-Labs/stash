"""Keep each session's event roll-up on the session row.

Listing sessions needed three facts per session — how many events, how big,
and when the last one landed — and computed all three by aggregating
history_events on every read. On a real account that meant scanning ~200k
event rows (4.5GB of buffers) to render a list of a few thousand rows, on
every page load. The facts are known at write time, so they live here.

Backfills every row, and creates a session row for any (owner, session_id)
that only existed as events — those were already visible on /sessions (its
query LEFT JOINed sessions) but invisible to the sidebar (which INNER JOINs),
so materializing without them would have dropped sessions from one view.

Revision ID: 0185
Revises: 0184
"""

from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE sessions
            ADD COLUMN last_event_at TIMESTAMPTZ,
            ADD COLUMN event_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN size_bytes BIGINT NOT NULL DEFAULT 0
        """
    )
    # Sessions that only ever existed as events get their row now, so the
    # session table is the single source of truth for what a session is.
    op.execute(
        """
        INSERT INTO sessions (owner_user_id, session_id, agent_name, created_by, started_at)
        SELECT h.owner_user_id,
               h.session_id,
               MAX(h.agent_name),
               (ARRAY_AGG(h.created_by ORDER BY h.created_at))[1],
               MIN(h.created_at)
        FROM history_events h
        WHERE h.session_id IS NOT NULL
          AND h.owner_user_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM sessions s
              WHERE s.owner_user_id = h.owner_user_id AND s.session_id = h.session_id
          )
        GROUP BY h.owner_user_id, h.session_id
        """
    )
    # The listing names a session's author. That used to come from the first
    # event's created_by; now it comes from the session row, so any row missing
    # it takes the same value it would have shown before.
    op.execute(
        """
        UPDATE sessions s
        SET created_by = e.created_by
        FROM (
            SELECT owner_user_id,
                   session_id,
                   (ARRAY_AGG(created_by ORDER BY created_at))[1] AS created_by
            FROM history_events
            WHERE session_id IS NOT NULL AND created_by IS NOT NULL
            GROUP BY owner_user_id, session_id
        ) e
        WHERE s.created_by IS NULL
          AND s.owner_user_id = e.owner_user_id
          AND s.session_id = e.session_id
        """
    )
    # size_bytes stays the stored (TOAST-compressed) size the old aggregate
    # reported, so numbers already on screen don't move.
    op.execute(
        """
        UPDATE sessions s
        SET event_count = a.event_count,
            size_bytes = a.size_bytes,
            last_event_at = a.last_event_at
        FROM (
            SELECT owner_user_id,
                   session_id,
                   COUNT(*)::INT AS event_count,
                   COALESCE(SUM(pg_column_size(content)), 0)::BIGINT AS size_bytes,
                   MAX(created_at) AS last_event_at
            FROM history_events
            WHERE session_id IS NOT NULL AND owner_user_id IS NOT NULL
            GROUP BY owner_user_id, session_id
        ) a
        WHERE s.owner_user_id = a.owner_user_id AND s.session_id = a.session_id
        """
    )
    # The listing order: newest activity first, within one owner's live rows.
    op.execute(
        """
        CREATE INDEX idx_sessions_recent ON sessions (owner_user_id, last_event_at DESC)
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sessions_recent")
    op.execute(
        "ALTER TABLE sessions "
        "DROP COLUMN last_event_at, DROP COLUMN event_count, DROP COLUMN size_bytes"
    )
