"""One grants table: skill access moves into `shares`.

`skill_members` rows become ordinary shares rows (object_type='skill',
principal_type='user'); the 'admin' tier collapses into 'write' — managing a
skill's shares is a workspace-member action, like every other object.
`skill_invites` (the in-app notification list) stays, but adopts the shares
permission vocabulary (read < comment < write).

A public "anyone with the link" grant is a shares row with
principal_type='public' and the all-zeros sentinel principal_id, so the
existing UNIQUE constraint caps it at one public row per object.

Revision ID: 0103
Revises: 0102
"""

from alembic import op

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO shares (workspace_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by, created_at)
        SELECT c.workspace_id, 'skill', sm.skill_id, 'user', sm.user_id,
               CASE WHEN sm.permission = 'admin' THEN 'write' ELSE sm.permission END,
               COALESCE(sm.granted_by, c.owner_id), sm.created_at
        FROM skill_members sm
        JOIN skills c ON c.id = sm.skill_id
        ON CONFLICT (object_type, object_id, principal_type, principal_id) DO NOTHING
        """)
    op.execute("DROP TABLE skill_members")

    op.execute("UPDATE skill_invites SET permission = 'write' WHERE permission = 'admin'")
    op.execute("ALTER TABLE skill_invites DROP CONSTRAINT IF EXISTS skill_invites_permission_check")
    op.execute(
        "ALTER TABLE skill_invites ADD CONSTRAINT skill_invites_permission_chk "
        "CHECK (permission IN ('read', 'comment', 'write'))"
    )


def downgrade() -> None:
    raise NotImplementedError("skill_members is gone; shares is the only grants table")
