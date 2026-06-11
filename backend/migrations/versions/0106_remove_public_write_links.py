"""Remove public write links.

Revision ID: 0106
Revises: 0105
"""

from alembic import op

revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE cartridges SET public_permission = 'read' WHERE public_permission = 'write'")
    op.execute("ALTER TABLE cartridges DROP CONSTRAINT IF EXISTS stashes_public_permission_check")
    op.execute(
        "ALTER TABLE cartridges DROP CONSTRAINT IF EXISTS cartridges_public_permission_check"
    )
    op.execute(
        "ALTER TABLE cartridges "
        "ADD CONSTRAINT cartridges_public_permission_check "
        "CHECK (public_permission IN ('none', 'read'))"
    )

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
        "ALTER TABLE cartridges DROP CONSTRAINT IF EXISTS cartridges_public_permission_check"
    )
    op.execute(
        "ALTER TABLE cartridges "
        "ADD CONSTRAINT cartridges_public_permission_check "
        "CHECK (public_permission IN ('none', 'read', 'write'))"
    )

    op.execute(
        "ALTER TABLE session_folders "
        "DROP CONSTRAINT IF EXISTS session_folders_public_permission_check"
    )
    op.execute(
        "ALTER TABLE session_folders "
        "ADD CONSTRAINT session_folders_public_permission_check "
        "CHECK (public_permission IN ('none', 'read', 'write'))"
    )
