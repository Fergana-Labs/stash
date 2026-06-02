"""Per-object sharing: the `shares` table.

The memo moves permissions onto files (not bundles). `shares` grants a principal
— a user (primary, team collaboration) or a cartridge (secondary, PLG link) —
access to an object. Folder / session-folder shares cascade to contents via the
recursive folder-chain in permission_service. Cartridge *contents* stay in
`cartridge_items`; cartridge *access* (who can open it) stays in `cartridge_members`.

Revision ID: 0082
Revises: 0081
"""

from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE shares (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id   uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            object_type    text NOT NULL,   -- file | page | folder | session | session_folder
            object_id      uuid NOT NULL,
            principal_type text NOT NULL,   -- user | cartridge
            principal_id   uuid NOT NULL,
            permission     text NOT NULL DEFAULT 'read',  -- read | write
            created_by     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at     timestamptz NOT NULL DEFAULT now(),
            UNIQUE (object_type, object_id, principal_type, principal_id)
        )
        """)
    op.execute("CREATE INDEX shares_principal_idx ON shares (principal_type, principal_id)")
    op.execute("CREATE INDEX shares_object_idx ON shares (object_type, object_id)")
    op.execute("CREATE INDEX shares_workspace_idx ON shares (workspace_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shares")
