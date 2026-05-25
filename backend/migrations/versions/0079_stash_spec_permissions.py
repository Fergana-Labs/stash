"""Align Stash sharing permissions with the product spec.

Revision ID: 0079
Revises: 0078
Create Date: 2026-05-21
"""

from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


_PERMISSIONS = "('none', 'view', 'comment', 'edit', 'manage')"
_MEMBER_PERMISSIONS = "('view', 'comment', 'edit', 'manage')"


def upgrade() -> None:
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_workspace_permission_check")
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_public_permission_check")
    op.execute("""
UPDATE stashes
SET
  workspace_permission = CASE workspace_permission
    WHEN 'read' THEN 'view'
    WHEN 'write' THEN 'edit'
    ELSE workspace_permission
  END,
  public_permission = CASE public_permission
    WHEN 'read' THEN 'view'
    WHEN 'write' THEN 'edit'
    ELSE public_permission
  END
""")
    op.execute(f"""
ALTER TABLE stashes
ADD CONSTRAINT stashes_workspace_permission_check
CHECK (workspace_permission IN {_PERMISSIONS})
""")
    op.execute(f"""
ALTER TABLE stashes
ADD CONSTRAINT stashes_public_permission_check
CHECK (public_permission IN {_PERMISSIONS})
""")

    op.execute("ALTER TABLE stash_members DROP CONSTRAINT IF EXISTS stash_members_permission_check")
    op.execute("""
UPDATE stash_members
SET permission = CASE permission
  WHEN 'read' THEN 'view'
  WHEN 'write' THEN 'edit'
  WHEN 'admin' THEN 'manage'
  ELSE permission
END
""")
    op.execute(f"""
ALTER TABLE stash_members
ADD CONSTRAINT stash_members_permission_check
CHECK (permission IN {_MEMBER_PERMISSIONS})
""")

    op.execute("ALTER TABLE stash_invites DROP CONSTRAINT IF EXISTS stash_invites_permission_check")
    op.execute("""
UPDATE stash_invites
SET permission = CASE permission
  WHEN 'read' THEN 'view'
  WHEN 'write' THEN 'edit'
  WHEN 'admin' THEN 'manage'
  ELSE permission
END
""")
    op.execute(f"""
ALTER TABLE stash_invites
ADD CONSTRAINT stash_invites_permission_check
CHECK (permission IN {_MEMBER_PERMISSIONS})
""")

    op.execute(
        "ALTER TABLE sessions "
        "ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE folders "
        "ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute("""
ALTER TABLE tables
ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb
""")


def downgrade() -> None:
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_workspace_permission_check")
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_public_permission_check")
    op.execute("""
UPDATE stashes
SET
  workspace_permission = CASE workspace_permission
    WHEN 'view' THEN 'read'
    WHEN 'comment' THEN 'read'
    WHEN 'edit' THEN 'write'
    WHEN 'manage' THEN 'write'
    ELSE workspace_permission
  END,
  public_permission = CASE public_permission
    WHEN 'view' THEN 'read'
    WHEN 'comment' THEN 'read'
    WHEN 'edit' THEN 'write'
    WHEN 'manage' THEN 'write'
    ELSE public_permission
  END
""")
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

    op.execute("ALTER TABLE stash_members DROP CONSTRAINT IF EXISTS stash_members_permission_check")
    op.execute("""
UPDATE stash_members
SET permission = CASE permission
  WHEN 'view' THEN 'read'
  WHEN 'comment' THEN 'read'
  WHEN 'edit' THEN 'write'
  WHEN 'manage' THEN 'admin'
  ELSE permission
END
""")
    op.execute("""
ALTER TABLE stash_members
ADD CONSTRAINT stash_members_permission_check
CHECK (permission IN ('read', 'write', 'admin'))
""")

    op.execute("ALTER TABLE stash_invites DROP CONSTRAINT IF EXISTS stash_invites_permission_check")
    op.execute("""
UPDATE stash_invites
SET permission = CASE permission
  WHEN 'view' THEN 'read'
  WHEN 'comment' THEN 'read'
  WHEN 'edit' THEN 'write'
  WHEN 'manage' THEN 'admin'
  ELSE permission
END
""")
    op.execute("""
ALTER TABLE stash_invites
ADD CONSTRAINT stash_invites_permission_check
CHECK (permission IN ('read', 'write', 'admin'))
""")

    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS metadata")
    op.execute("ALTER TABLE folders DROP COLUMN IF EXISTS metadata")
    op.execute("ALTER TABLE tables DROP COLUMN IF EXISTS metadata")
