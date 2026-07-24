"""Install counter on published skills.

`view_count` measures curiosity; `install_count` measures adoption — how many
times `stash skills install <slug>` actually materialized this skill into an
agent's skills directory. Incremented by the CLI's post-install ping.

Revision ID: 0162
Revises: 0161
"""

from alembic import op

revision = "0162"
down_revision = "0161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE skills ADD COLUMN install_count integer NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE skills DROP COLUMN install_count")
