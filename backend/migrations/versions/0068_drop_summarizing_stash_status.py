"""Reserved cleanup revision for removed session-bundle stash status.

The old session-bundle `stashes.status` column is gone from the current
product Stash schema, so there is no status constraint left to narrow.

Revision ID: 0068
Revises: 0067
"""

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
