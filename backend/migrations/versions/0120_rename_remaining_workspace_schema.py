"""Rename the last workspace-named schema objects.

Final cleanup of the "workspace" vocabulary at the schema level:
- workspace_sources -> user_sources (connected sources are per-user). FK
  constraints from the per-integration document tables follow the rename
  automatically.
- gong_documents.gong_workspace_id -> gong_account_id (it identifies the Gong
  account, not a Stash workspace).
- session_folders.workspace_permission is dropped: it granted access to
  workspace members, which no longer exist; access is owner + shares + public.

Revision ID: 0120
Revises: 0119
"""

from alembic import op

revision = "0120"
down_revision = "0119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workspace_sources RENAME TO user_sources")
    op.execute("ALTER TABLE gong_documents RENAME COLUMN gong_workspace_id TO gong_account_id")
    op.execute("ALTER TABLE session_folders DROP COLUMN IF EXISTS workspace_permission")


def downgrade() -> None:
    raise NotImplementedError("Schema vocabulary cleanup is one-way.")
