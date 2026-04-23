"""Drop the personal (workspace_id IS NULL) scope.

The personal variants of notebooks / tables / files / history_events /
decks are being removed from the product — everything lives in a
workspace. Prod has zero NULL workspace_id rows across every surface,
so this migration just promotes the columns to NOT NULL.

Revision ID: 0015
Revises: 0014
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fail loudly if any row still has NULL — we verified prod is clean,
    # but a fresh dev DB might have legacy data; making the caller deal
    # with it is safer than silently dropping rows.
    for table in ("notebooks", "tables", "files", "history_events", "decks"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN workspace_id SET NOT NULL")


def downgrade() -> None:
    for table in ("notebooks", "tables", "files", "history_events", "decks"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN workspace_id DROP NOT NULL")
