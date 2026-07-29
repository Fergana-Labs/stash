"""Link a url_imports row to the Bookmarks row it will fill in.

A bookmark used to appear only once the worker had fetched its page, so a bulk
import looked like nothing had happened until content started landing —
seconds on a quiet queue, days behind a large backfill. The row is now created
when the import is accepted and updated in place when the content arrives, and
this column is how the worker finds the row it owns.

ON DELETE SET NULL, not CASCADE: deleting a bookmark from the grid must not
erase the record that we already imported that URL, or existing_urls would
stop deduping it and the next import would happily fetch it again.

Imports already queued when this ships have no row to point at (NULL). They
take the same path an interactive single-page clip does — insert on landing —
which is a branch clip_service needs permanently anyway.

Revision ID: 0175
Revises: 0174
"""

from alembic import op

revision = "0175"
down_revision = "0174"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE url_imports ADD COLUMN bookmark_row_id uuid "
        "REFERENCES table_rows(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE url_imports DROP COLUMN bookmark_row_id")
