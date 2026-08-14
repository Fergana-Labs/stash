"""Sharing has two levels again: read and write.

The 'comment' tier earned its keep nowhere — it was a third option in every
share dialog that granted read plus one niche verb. Existing comment grants
downgrade to read (never a silent upgrade to write); commenting itself now
requires write access.

Revision ID: 0186
Revises: 0185
"""

from alembic import op

revision = "0186"
down_revision = "0185"
branch_labels = None
depends_on = None

_PUBLIC_TABLES = ("pages", "files", "folders", "tables")


def upgrade() -> None:
    for table in ("shares", "share_invites"):
        op.execute(f"UPDATE {table} SET permission = 'read' WHERE permission = 'comment'")
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_permission_chk")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_permission_chk "
            f"CHECK (permission IN ('read', 'write'))"
        )
    for table in _PUBLIC_TABLES:
        op.execute(
            f"UPDATE {table} SET public_permission = 'read' WHERE public_permission = 'comment'"
        )
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_public_permission_check")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_public_permission_check "
            f"CHECK (public_permission IN ('none', 'read', 'write'))"
        )


def downgrade() -> None:
    for table in ("shares", "share_invites"):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_permission_chk")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_permission_chk "
            f"CHECK (permission IN ('read', 'comment', 'write'))"
        )
    for table in _PUBLIC_TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_public_permission_check")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_public_permission_check "
            f"CHECK (public_permission IN ('none', 'read', 'comment', 'write'))"
        )
