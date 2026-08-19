"""Remove connected-source sharing.

Connected integrations belong to the user who connected them. Stash no longer
lets another user read data through the owner's provider connection.

Revision ID: 0186
Revises: 0185
"""

from alembic import op

revision = "0186"
down_revision = "0185"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM shares WHERE object_type = 'source'")
    op.execute("DELETE FROM share_invites WHERE object_type = 'source'")


def downgrade() -> None:
    pass
