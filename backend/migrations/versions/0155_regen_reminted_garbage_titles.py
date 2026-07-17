"""Repeat the 0154 garbage-title sweep for rows re-minted by the old prompt.

0154 deleted the legacy garbage titles, but the regeneration backlog was
processed by the old prompt (this deploy is what fixes it), which re-minted
reply-shaped titles for ~60% of them. Same delete, same patterns: this runs
at boot before the fixed pipeline starts, so everything regenerates clean.

Revision ID: 0155
Revises: 0154
Create Date: 2026-07-16
"""

from alembic import op

revision = "0155"
down_revision = "0154"
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
