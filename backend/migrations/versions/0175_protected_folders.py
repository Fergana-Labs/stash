"""Mark the folders the product structurally depends on as protected.

Memory was already undeletable, via its own is_memory flag. Clips was not:
renaming it made the extension quietly fill a fresh empty one, and deleting it
took every clip with it. Both are structural — code resolves them by identity
and writes into them — so they get one flag and one guard instead of a
per-folder special case.

is_memory stays: it answers "which folder is Memory" (identity), which is a
different question from "may this be renamed" (policy).

Revision ID: 0174
Revises: 0173
"""

from alembic import op

revision = "0175"
down_revision = "0174"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE folders ADD COLUMN is_protected boolean NOT NULL DEFAULT false")
    op.execute("UPDATE folders SET is_protected = true WHERE is_memory")
    # Existing Clips folders are identified the way clip_service already
    # identifies them: by name at the scope root. A nested folder called Clips
    # is somebody's own, not ours.
    op.execute(
        "UPDATE folders SET is_protected = true WHERE parent_folder_id IS NULL AND name = 'Clips'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE folders DROP COLUMN is_protected")
