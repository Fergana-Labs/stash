"""Split Stash general access into workspace and public roles.

Revision ID: 0062
Revises: 0061
"""

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE stashes
ADD COLUMN IF NOT EXISTS workspace_permission VARCHAR(16) NOT NULL DEFAULT 'read'
""")
    op.execute("""
ALTER TABLE stashes
ADD COLUMN IF NOT EXISTS public_permission VARCHAR(16) NOT NULL DEFAULT 'none'
""")
    op.execute("""
UPDATE stashes
SET
  workspace_permission = CASE
    WHEN access = 'private' THEN 'none'
    ELSE 'read'
  END,
  public_permission = CASE
    WHEN access = 'public' THEN 'read'
    ELSE 'none'
  END
""")
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_access_check")
    op.execute("ALTER TABLE stashes DROP COLUMN IF EXISTS access")
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_workspace_permission_check")
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_public_permission_check")
    op.execute("""
ALTER TABLE stashes
ADD CONSTRAINT stashes_workspace_permission_check
CHECK (workspace_permission IN ('none', 'read', 'write'))
""")
    op.execute("""
ALTER TABLE stashes
ADD CONSTRAINT stashes_public_permission_check
CHECK (public_permission IN ('none', 'read', 'write'))
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE stashes
ADD COLUMN IF NOT EXISTS access VARCHAR(16) NOT NULL DEFAULT 'workspace'
""")
    op.execute("""
UPDATE stashes
SET access = CASE
  WHEN public_permission != 'none' THEN 'public'
  WHEN workspace_permission != 'none' THEN 'workspace'
  ELSE 'private'
END
""")
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_workspace_permission_check")
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_public_permission_check")
    op.execute("ALTER TABLE stashes DROP COLUMN IF EXISTS workspace_permission")
    op.execute("ALTER TABLE stashes DROP COLUMN IF EXISTS public_permission")
    op.execute("""
ALTER TABLE stashes
ADD CONSTRAINT stashes_access_check CHECK (access IN ('workspace', 'private', 'public'))
""")
