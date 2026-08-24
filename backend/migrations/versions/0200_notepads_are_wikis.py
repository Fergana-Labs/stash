"""Rename notepads to per-user wikis.

"Notepad" was planning-era vocabulary for the per-user memory surface. Every
product surface — the console, the pricing page, the wiki-graph endpoints —
already calls it the user's own wiki, so the schema catches up: the surface
is a wiki like the shared one, just scoped to one end user and never
anonymized. Nothing anywhere says notepad.

Pure rename plus the one user-visible data change: each workspace's
"User Notepads" folder becomes "User Wikis".

Revision ID: 0200
Revises: 0199
"""

from alembic import op

revision = "0200"
down_revision = "0199"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE end_users RENAME COLUMN notepad_folder_id TO wiki_folder_id")
    op.execute(
        "ALTER TABLE workspaces RENAME COLUMN end_user_notepads_folder_id "
        "TO end_user_wikis_folder_id"
    )
    op.execute(
        "UPDATE folders SET name = 'User Wikis' "
        "WHERE id IN (SELECT end_user_wikis_folder_id FROM workspaces) "
        "  AND name = 'User Notepads'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE folders SET name = 'User Notepads' "
        "WHERE id IN (SELECT end_user_wikis_folder_id FROM workspaces) "
        "  AND name = 'User Wikis'"
    )
    op.execute(
        "ALTER TABLE workspaces RENAME COLUMN end_user_wikis_folder_id "
        "TO end_user_notepads_folder_id"
    )
    op.execute("ALTER TABLE end_users RENAME COLUMN wiki_folder_id TO notepad_folder_id")
