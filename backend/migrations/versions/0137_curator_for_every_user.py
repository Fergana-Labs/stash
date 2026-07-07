"""Provision the Memory curator for every existing user.

Curator creation moved from lazy (first chat/channel turn) to signup, so
API-key-only production accounts get sleep-time curation. One-shot backfill
for accounts that predate the change. Mirrors get_or_create_curator: a
per-user staggered daily cron, baseline and watermark seeded to a bounded
backfill point so the first run bootstraps from real history.

Revision ID: 0137
Revises: 0136
"""

from alembic import op

revision = "0137"
down_revision = "0136"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO agents (user_id, name, run_mode, schedule_cron, is_curator,
                            last_run_at, curated_through)
        SELECT u.id, 'Memory curator', 'scheduled',
               mod(('x' || substr(md5(u.id::text), 1, 7))::bit(28)::int, 60)::text
                 || ' '
                 || mod(('x' || substr(md5(u.id::text), 8, 7))::bit(28)::int, 24)::text
                 || ' * * *',
               true,
               greatest(u.created_at, now() - interval '90 days'),
               greatest(u.created_at, now() - interval '90 days')
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.is_curator
        )
        """
    )


def downgrade() -> None:
    pass
