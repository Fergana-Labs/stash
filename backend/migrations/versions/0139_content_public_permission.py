"""Per-object "anyone with the link" access for pages, files, folders, tables.

Google-Docs-style general access: each row carries a public_permission granting
everyone (including anonymous readers) access at that level and above —
read < comment < write. A folder's grant cascades to its descendants, resolved
at read time in permission_service. Person shares (the `shares` table) are
unchanged; this is the link-level grant that sits alongside them.

Revision ID: 0139
Revises: 0138
"""

from alembic import op

revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None

_TABLES = ("pages", "files", "folders", "tables")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD COLUMN public_permission varchar(16) NOT NULL DEFAULT 'none', "
            f"ADD CONSTRAINT {table}_public_permission_check "
            f"CHECK (public_permission IN ('none', 'read', 'comment', 'write'))"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN public_permission")
