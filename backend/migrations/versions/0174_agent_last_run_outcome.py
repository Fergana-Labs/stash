"""Record how each scheduled-agent tick resolved.

mark_run consumes the cron tick up front (last_run_at), after which a run
either executes, fails, or is skipped by one of three designed gates (credit
allowance, missing credential, no changes since the watermark). Only failures
left a trace (last_run_error), so from the outside a healthy skip was
indistinguishable from a run that died mid-flight — the confusion behind the
July 2026 "curator silently stopped" incident, and again on Aug 2 when a
correct no-changes skip for an enterprise customer read as a silent death.

last_run_outcome makes every tick legible: mark_run stamps 'started', which
then resolves to 'ran', 'failed', or 'skipped_<reason>'. A row still at
'started' means the run died without resolving — the stale-curator watchdog
pages on that. NULL means no tick since this column shipped.
"""

from alembic import op

revision = "0174"
down_revision = "0173"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agents ADD COLUMN last_run_outcome text")


def downgrade() -> None:
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS last_run_outcome")
