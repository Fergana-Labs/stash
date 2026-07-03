"""Require session_id on every history event.

Session-less history_events were never a designed concept: a plugin bug
(hooks reading the session id from local state instead of the hook payload)
silently pushed transcript events with no session pointer, and the access
predicate grew a special "bookkeeping rows" carve-out to accommodate them.
The plugin bug is fixed and the API now rejects events without a session_id,
so the orphaned rows are deleted and the column becomes NOT NULL — one row
shape, one access rule (an event is readable iff its session is readable).

Revision ID: 0121
Revises: 0120
"""

from alembic import op

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM history_events WHERE session_id IS NULL")
    op.execute("ALTER TABLE history_events ALTER COLUMN session_id SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE history_events ALTER COLUMN session_id DROP NOT NULL")
