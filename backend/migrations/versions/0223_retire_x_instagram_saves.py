"""Retire the X and Instagram saves integrations.

Revision ID: 0223
Revises: 0222
"""

from alembic import op

revision = "0223"
down_revision = "0222"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The indexers are gone. An enabled row with no indexer stays "due" forever
    # and starves real syncs out of the due_sources window (see 0101), so stop
    # syncing these sources. Their archived documents are kept and stay readable.
    op.execute("""
        UPDATE user_sources SET
            sync_enabled = false, sync_status = 'idle', sync_error = NULL, sync_warning = NULL,
            sync_task_id = NULL, sync_claimed_at = NULL, sync_started_at = NULL
        WHERE source_type IN ('x_saves', 'instagram_saves')
    """)
    # The X provider is no longer registered, so its stored OAuth grants can
    # never be used or refreshed again.
    op.execute("DELETE FROM user_integrations WHERE provider = 'x'")


def downgrade() -> None:
    # Deliberately not reverted: re-enabling sync without an indexer would
    # re-introduce the queue starvation, and the deleted grants are unrecoverable.
    pass
