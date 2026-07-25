"""Restore the real start time on sessions created by a history import.

`sessions.started_at` defaults to now() and the transcript upload never set it,
so an import stamped every session with the moment it ran. One user's first day
put 116 sessions spanning April to July at a single timestamp three minutes
wide; anything ordered by started_at files them all under the import date.

The transcript carries the original event times, and the importer marks its own
event with source='history_import'. That marker scopes this to imported
sessions only, so live sessions — whose events are seconds from their
started_at — are never touched by clock skew.

Irreversible: the overwritten value was the import timestamp, which carried no
information about the session itself.

Revision ID: 0167
Revises: 0166
Create Date: 2026-07-25
"""

from alembic import op

revision = "0167"
down_revision = "0166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE sessions s
        SET started_at = first_events.first_event
        FROM (
            SELECT owner_user_id, session_id, MIN(created_at) AS first_event
            FROM history_events
            GROUP BY owner_user_id, session_id
        ) AS first_events
        WHERE first_events.owner_user_id = s.owner_user_id
          AND first_events.session_id = s.session_id
          AND first_events.first_event < s.started_at
          AND EXISTS (
              SELECT 1 FROM history_events marker
              WHERE marker.owner_user_id = s.owner_user_id
                AND marker.session_id = s.session_id
                AND marker.metadata->>'source' = 'history_import'
          )
        """)


def downgrade() -> None:
    pass
