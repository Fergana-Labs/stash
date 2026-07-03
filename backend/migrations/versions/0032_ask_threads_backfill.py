"""Backfill ask_threads / ask_messages on production.

Production's alembic_version sat at "0027" before the merge renumber,
but that "0027" was the old session_bundles migration — meaning new-0027
(ask_threads) was skipped on prod. This migration creates those tables
idempotently so prod converges with dev.

Revision ID: 0032
Revises: 0031
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS ask_threads ("
        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,"
        "  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "  title TEXT NOT NULL DEFAULT '',"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ask_threads_user_workspace "
        "ON ask_threads(user_id, workspace_id, updated_at DESC)"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS ask_messages ("
        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  thread_id UUID NOT NULL REFERENCES ask_threads(id) ON DELETE CASCADE,"
        "  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),"
        "  content TEXT NOT NULL DEFAULT '',"
        "  citations JSONB NOT NULL DEFAULT '[]'::jsonb,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ask_messages_thread ON ask_messages(thread_id, created_at)"
    )


def downgrade() -> None:
    # No-op: prod and dev are converged after this point and original
    # creation lives in 0027_ask_threads. Don't double-drop.
    pass
