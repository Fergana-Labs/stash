"""One grants table: cartridge access moves into `shares`.

`cartridge_members` rows become ordinary shares rows (object_type='stash',
principal_type='user'); the 'admin' tier collapses into 'write' — managing a
cartridge's shares is a workspace-member action, like every other object.
`cartridge_invites` (the in-app notification list) stays, but adopts the
shares permission vocabulary (read < comment < write).

A public "anyone with the link" grant is a shares row with
principal_type='public' and the all-zeros sentinel principal_id, so the
existing UNIQUE constraint caps it at one public row per object.

Revision ID: 0102
Revises: 0101
"""

from alembic import op

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO shares (workspace_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by, created_at)
        SELECT c.workspace_id, 'stash', cm.cartridge_id, 'user', cm.user_id,
               CASE WHEN cm.permission = 'admin' THEN 'write' ELSE cm.permission END,
               COALESCE(cm.granted_by, c.owner_id), cm.created_at
        FROM cartridge_members cm
        JOIN cartridges c ON c.id = cm.cartridge_id
        ON CONFLICT (object_type, object_id, principal_type, principal_id) DO NOTHING
        """)
    op.execute("DROP TABLE cartridge_members")

    op.execute("UPDATE cartridge_invites SET permission = 'write' WHERE permission = 'admin'")
    # The inline CHECK from 0057 kept its auto-generated name through the
    # 0081 table rename; drop both spellings to be safe.
    op.execute(
        "ALTER TABLE cartridge_invites DROP CONSTRAINT IF EXISTS stash_invites_permission_check"
    )
    op.execute(
        "ALTER TABLE cartridge_invites DROP CONSTRAINT IF EXISTS cartridge_invites_permission_check"
    )
    op.execute(
        "ALTER TABLE cartridge_invites ADD CONSTRAINT cartridge_invites_permission_chk "
        "CHECK (permission IN ('read', 'comment', 'write'))"
    )


def downgrade() -> None:
    raise NotImplementedError("cartridge_members is gone; shares is the only grants table")
