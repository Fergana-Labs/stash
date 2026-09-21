"""Give source syncs a single claim and track freshness alerts.

Revision ID: 0206
Revises: 0205
"""

from alembic import op

revision = "0206"
down_revision = "0205"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_sources
            ADD COLUMN sync_task_id text,
            ADD COLUMN sync_claimed_at timestamptz,
            ADD COLUMN sync_started_at timestamptz,
            ADD COLUMN sync_alerted_at timestamptz
    """)
    # Old queued jobs have no claim and will be discarded by the worker.
    # Reconcile replaces them once, without losing any indexed content.
    op.execute("""
        UPDATE user_sources SET sync_status = 'idle', next_sync_at = now()
        WHERE sync_status = 'syncing'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_sources DROP COLUMN sync_task_id,
            DROP COLUMN sync_claimed_at, DROP COLUMN sync_started_at,
            DROP COLUMN sync_alerted_at
    """)
