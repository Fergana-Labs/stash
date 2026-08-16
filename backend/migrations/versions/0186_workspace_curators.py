"""Every workspace scope gets a Memory curator.

New workspaces create theirs in `create_workspace`; this backfills the
workspaces that already exist. Mirrors `agent_service.get_or_create_curator`:
scheduled nightly (staggered off the scope user's id), with the cron baseline
and delta watermark seeded to a bounded backfill point so the first run is
due immediately and bootstraps the team wiki from real history.

Revision ID: 0186
Revises: 0185
"""

from uuid import UUID

from alembic import op

revision = "0186"
down_revision = "0185"
branch_labels = None
depends_on = None

# Copied from agent_service (migrations don't import app code); the exact
# stagger only spreads load inside the nightly window, so drift is harmless.
_BACKFILL_DAYS = 90
_WINDOW_START_HOUR_UTC = 8
_WINDOW_HOURS = 4


def _staggered_nightly_cron(user_id: UUID) -> str:
    n = int.from_bytes(user_id.bytes, "big")
    hour = _WINDOW_START_HOUR_UTC + (n // 60) % _WINDOW_HOURS
    return f"{n % 60} {hour} * * *"


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        "SELECT w.scope_user_id FROM workspaces w "
        "WHERE NOT EXISTS (SELECT 1 FROM agents a "
        "                  WHERE a.user_id = w.scope_user_id AND a.is_curator)"
    ).fetchall()
    for (scope_user_id,) in rows:
        bind.exec_driver_sql(
            "INSERT INTO agents (user_id, name, run_mode, schedule_cron, is_curator, "
            "                    last_run_at, curated_through) "
            "SELECT u.id, 'Memory curator', 'scheduled', %(cron)s, true, "
            "       greatest(u.created_at, now() - make_interval(days => %(days)s)), "
            "       greatest(u.created_at, now() - make_interval(days => %(days)s)) "
            "FROM users u WHERE u.id = %(scope_user_id)s",
            {
                "cron": _staggered_nightly_cron(UUID(str(scope_user_id))),
                "days": _BACKFILL_DAYS,
                "scope_user_id": scope_user_id,
            },
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM agents WHERE is_curator AND user_id IN (SELECT scope_user_id FROM workspaces)"
    )
