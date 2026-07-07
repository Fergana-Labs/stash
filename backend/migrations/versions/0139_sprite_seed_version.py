"""Track which seed-script version a sprite was set up with.

Sprites are seeded once at provision, so seed additions (e.g. the opencode
install) never reached boxes provisioned earlier — their managed-harness runs
died with "command not found". Existing rows default to 0 (stale), so every
old box re-seeds on its next acquire.

Revision ID: 0139
Revises: 0138
"""

from alembic import op

revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_sprites ADD COLUMN seed_version integer NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE user_sprites DROP COLUMN seed_version")
