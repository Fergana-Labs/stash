"""Flatten history stores: move workspace_id directly onto history_events, drop histories table.

Before: history_events.store_id → histories.workspace_id
After:  history_events.workspace_id (direct)

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add workspace_id and created_by columns to history_events
    op.execute("""
        ALTER TABLE history_events
        ADD COLUMN workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
        ADD COLUMN created_by UUID REFERENCES users(id)
    """)

    # 2. Backfill from histories table
    op.execute("""
        UPDATE history_events he
        SET workspace_id = h.workspace_id,
            created_by = h.created_by
        FROM histories h
        WHERE he.store_id = h.id
    """)

    # 3. Drop store_id FK and column
    op.execute("ALTER TABLE history_events DROP COLUMN store_id")

    # 4. Add index on workspace_id
    op.execute("CREATE INDEX idx_history_events_workspace ON history_events (workspace_id)")
    op.execute("CREATE INDEX idx_history_events_agent_session ON history_events (agent_name, session_id)")

    # 5. Drop the histories table
    # First drop any references from other tables
    op.execute("DELETE FROM object_permissions WHERE object_type = 'history'")
    op.execute("DELETE FROM object_shares WHERE object_type = 'history'")

    # Drop sleep_watermarks FK if it exists
    op.execute("""
        ALTER TABLE sleep_watermarks DROP CONSTRAINT IF EXISTS sleep_watermarks_store_id_fkey
    """)
    op.execute("DROP TABLE IF EXISTS sleep_watermarks")
    op.execute("DROP TABLE IF EXISTS histories CASCADE")


def downgrade() -> None:
    # Re-create histories table
    op.execute("""
        CREATE TABLE IF NOT EXISTS histories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
            name VARCHAR(128) NOT NULL,
            description TEXT DEFAULT '',
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(workspace_id, name)
        )
    """)

    # Re-add store_id column
    op.execute("""
        ALTER TABLE history_events
        ADD COLUMN store_id UUID REFERENCES histories(id) ON DELETE CASCADE
    """)

    # Drop new columns
    op.execute("DROP INDEX IF EXISTS idx_history_events_workspace")
    op.execute("DROP INDEX IF EXISTS idx_history_events_agent_session")
    op.execute("ALTER TABLE history_events DROP COLUMN IF EXISTS workspace_id")
    op.execute("ALTER TABLE history_events DROP COLUMN IF EXISTS created_by")
