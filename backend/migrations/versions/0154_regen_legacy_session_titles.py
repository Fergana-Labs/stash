"""Drop legacy garbage session titles so the current pipeline regenerates them.

The 2026-05-21 bulk title backfill stored titles that are markdown-wrapped,
truncated mid-sentence at the 80-char cap, or just an assistant reply echoed
back ("You're right—I apologize for the confusion"). Their source_hash still
matches, so the staleness check never refreshes them. Deleting the rows makes
them "missing": the reconcile_missing beat task and lazy enqueue on listing
regenerate them with the current prompt + cleaning.

A false positive is harmless — the row just regenerates through the same
good pipeline. user_set titles are never touched.

Revision ID: 0154
Revises: 0153
Create Date: 2026-07-16
"""

from alembic import op

revision = "0154"
down_revision = "0153"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM session_titles
        WHERE user_set = FALSE
          AND (
            title LIKE '**%'
            OR title LIKE '#%'
            OR length(title) >= 78
            OR title ~ $re$^(You're |You are |I'll |I've |I ap|I don't |I need |I appreciate |Yes[,— .]|Your |Good |Great |Perfect|Looking |pong$)$re$
          )
        """)


def downgrade() -> None:
    pass
