"""Skill sharing follows folders; the skills table becomes a pure publish record.

Person-to-person skill access now rides the generic ``shares`` table on the
skill's folder (folder shares already cascade read to the subtree), so
``skill_members`` and ``skill_invites`` are dropped — existing member grants
convert to folder shares first.

A publish record now *means* "publicly readable at /skills/<slug>", so the
``workspace_permission`` / ``public_permission`` columns go away. Records that
were never public (``public_permission = 'none'``) are deleted — their folder
stays a skill, and the member grants they carried live on as folder shares.

Revision ID: 0104
Revises: 0103
"""

from alembic import op

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Member grants become folder shares (admin managed the record, which is
    # now owner-only; their content access maps to write).
    op.execute("""
        INSERT INTO shares (workspace_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by)
        SELECT s.workspace_id, 'folder', s.folder_id, 'user', sm.user_id,
               CASE WHEN sm.permission = 'read' THEN 'read' ELSE 'write' END,
               COALESCE(sm.granted_by, s.owner_id)
        FROM skill_members sm
        JOIN skills s ON s.id = sm.skill_id
        ON CONFLICT (object_type, object_id, principal_type, principal_id) DO NOTHING
        """)
    op.execute("DROP TABLE skill_invites")
    op.execute("DROP TABLE skill_members")

    op.execute("DELETE FROM skills WHERE public_permission = 'none'")
    op.execute("ALTER TABLE skills DROP COLUMN workspace_permission")
    op.execute("ALTER TABLE skills DROP COLUMN public_permission")


def downgrade() -> None:
    # Schema-honest: every surviving record was public.
    op.execute(
        "ALTER TABLE skills ADD COLUMN workspace_permission VARCHAR(8) NOT NULL DEFAULT 'read' "
        "CONSTRAINT skills_workspace_permission_check "
        "CHECK (workspace_permission IN ('none', 'read', 'write'))"
    )
    op.execute(
        "ALTER TABLE skills ADD COLUMN public_permission VARCHAR(8) NOT NULL DEFAULT 'read' "
        "CONSTRAINT skills_public_permission_check "
        "CHECK (public_permission IN ('none', 'read', 'write'))"
    )
    op.execute("""
        CREATE TABLE skill_members (
            skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            permission VARCHAR(8) NOT NULL DEFAULT 'read'
                CONSTRAINT skill_members_permission_check
                CHECK (permission IN ('read', 'write', 'admin')),
            granted_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT skill_members_pkey PRIMARY KEY (skill_id, user_id)
        )
        """)
    op.execute("CREATE INDEX idx_skill_members_user ON skill_members (user_id)")
    op.execute("""
        CREATE TABLE skill_invites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            recipient_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invited_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            target_workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,
            permission VARCHAR(8) NOT NULL DEFAULT 'read'
                CONSTRAINT skill_invites_permission_check
                CHECK (permission IN ('read', 'write', 'admin')),
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CONSTRAINT skill_invites_status_check
                CHECK (status IN ('pending', 'accepted', 'dismissed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT skill_invites_skill_id_recipient_user_id_key
                UNIQUE (skill_id, recipient_user_id)
        )
        """)
    op.execute(
        "CREATE INDEX idx_skill_invites_recipient_status "
        "ON skill_invites (recipient_user_id, status, created_at DESC)"
    )
