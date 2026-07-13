"""Give session folders an optional caller-owned external key.

get-or-create matched folders by exact name, which made renaming a folder in
the UI break the caller's mapping (the next call recreated the folder under
the old name). An external key — unique per owner, chosen by the caller, e.g.
a customer app's org id — separates identity from display: get-or-create
matches on the key and the name becomes freely renamable.

Revision ID: 0143
Revises: 0142
"""

from alembic import op

revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE session_folders ADD COLUMN external_key varchar(128)")
    op.execute(
        "CREATE UNIQUE INDEX session_folders_owner_external_key "
        "ON session_folders (owner_user_id, external_key) "
        "WHERE external_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS session_folders_owner_external_key")
    op.execute("ALTER TABLE session_folders DROP COLUMN IF EXISTS external_key")
