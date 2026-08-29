"""Knowledge-map projections plot one point per session, not per event.

Cached rows hold per-event points with source "history_events", which the new
compute never produces — the cache is truncated so everything recomputes in
the session-level shape on next load.

Revision ID: 0206
Revises: 0205
"""

from alembic import op

revision = "0206"
down_revision = "0205"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE embedding_projections")


def downgrade() -> None:
    op.execute("TRUNCATE embedding_projections")
