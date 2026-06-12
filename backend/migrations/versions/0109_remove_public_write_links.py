"""Remove public write links from session folders.

Skills no longer carry permission columns (0104 made them pure publish
records), so only session folders still need the write -> read cutover.

Revision ID: 0109
Revises: 0108
"""

from alembic import op

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
UPDATE session_folders
SET public_permission = 'read'
WHERE public_permission = 'write'
""")
    op.execute(
        "ALTER TABLE session_folders "
        "DROP CONSTRAINT IF EXISTS session_folders_public_permission_check"
    )
    op.execute(
        "ALTER TABLE session_folders "
        "ADD CONSTRAINT session_folders_public_permission_check "
        "CHECK (public_permission IN ('none', 'read'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE session_folders "
        "DROP CONSTRAINT IF EXISTS session_folders_public_permission_check"
    )
    op.execute(
        "ALTER TABLE session_folders "
        "ADD CONSTRAINT session_folders_public_permission_check "
        "CHECK (public_permission IN ('none', 'read', 'write'))"
    )
