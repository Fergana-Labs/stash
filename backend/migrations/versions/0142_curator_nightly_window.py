"""Move every Memory curator's cron into the nightly quiet window.

Curator crons were staggered across all 24 hours, so some ran during US work
hours — while users were actively adding content and while deploys were
restarting the Celery worker (a killed run consumes its tick and is lost until
the next day). Now they stagger within 08:00–11:59 UTC (midnight–4am Pacific),
matching _staggered_nightly_cron for new signups. The SQL hash differs from
the Python one; only the window has to match, any stable stagger works.

Revision ID: 0142
Revises: 0141
"""

from alembic import op

revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE agents
        SET schedule_cron =
            mod(('x' || substr(md5(user_id::text), 1, 7))::bit(28)::int, 60)::text
              || ' '
              || (8 + mod(('x' || substr(md5(user_id::text), 8, 7))::bit(28)::int, 4))::text
              || ' * * *'
        WHERE is_curator
        """
    )


def downgrade() -> None:
    pass
