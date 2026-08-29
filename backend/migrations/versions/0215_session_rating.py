"""Sessions carry a user rating (good / bad).

A rating is the user's own verdict on a session — a quick label while
browsing traces so the good ones can be found again and the bad ones stand
out. It is stored on the session row, not on events, because it describes
the session as a whole."""

from alembic import op

revision = "0215"
down_revision = "0214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN rating text CHECK (rating IN ('good', 'bad'))")


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP COLUMN rating")
