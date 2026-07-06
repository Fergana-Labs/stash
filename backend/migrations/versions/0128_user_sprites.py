"""Per-user cloud computers (Fly Sprites).

Each user gets one persistent sprite VM running their agent. This table is the
registry mapping users to sprite names, deliberately substrate-thin so a later
port to self-managed VMs only swaps the service layer, not the schema.

Revision ID: 0128
Revises: 0127
"""

from alembic import op

revision = "0128"
down_revision = "0127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_sprites (
            user_id        uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            sprite_name    text NOT NULL UNIQUE,
            status         text NOT NULL,
            last_active_at timestamptz NOT NULL DEFAULT now(),
            created_at     timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_sprites")
