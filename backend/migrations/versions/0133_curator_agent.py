"""The reserved per-user Memory curator agent.

A daily sleep-time agent that curates the user's Memory into an LLM wiki. It's
a normal scheduled agent (so the existing beat task runs it) flagged
is_curator so it's reserved (auto-provisioned, not deletable) and gets the
curation prompt instead of a user schedule_prompt.

Revision ID: 0133
Revises: 0132
"""

from alembic import op

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agents ADD COLUMN is_curator boolean NOT NULL DEFAULT false")
    op.execute("CREATE UNIQUE INDEX one_curator_per_user ON agents (user_id) WHERE is_curator")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS one_curator_per_user")
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS is_curator")
