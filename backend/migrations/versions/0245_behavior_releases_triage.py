"""Release markers, root-cause triage runs, eval drift alerts, and trace task types.

A release marker says "the agent changed here" so a behavior's rate can be
compared before and after. A triage run investigates a behavior's recent hits
and groups them into root causes. Evals can alert when their production
agreement drifts. Task types name what each trace was asked to do, for cohorts.

Revision ID: 0245
Revises: 0244
"""

from alembic import op

revision = "0245"
down_revision = "0244"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE agent_releases (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        agent text,
        label text NOT NULL CHECK (length(label) BETWEEN 1 AND 120),
        note text NOT NULL DEFAULT '',
        released_at timestamptz NOT NULL DEFAULT now(),
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE INDEX agent_releases_owner ON agent_releases (owner_user_id, released_at DESC)"
    )

    op.execute("""CREATE TABLE behavior_triage (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        behavior_id uuid NOT NULL REFERENCES behaviors(id) ON DELETE CASCADE,
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'failed')),
        result jsonb,
        error text,
        created_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz
    )""")
    op.execute(
        "CREATE INDEX behavior_triage_behavior ON behavior_triage (behavior_id, created_at DESC)"
    )
    op.execute(
        "ALTER TABLE behavior_alerts ADD COLUMN triage_id uuid REFERENCES behavior_triage(id) ON DELETE SET NULL"
    )

    # A reviewer's reason for confirming or rejecting a hit; the detector learns from it.
    op.execute("ALTER TABLE behavior_hits ADD COLUMN review_note text NOT NULL DEFAULT ''")

    # Eval drift alerts: {"min_agreement": 0.8, "cooldown_hours": 24, "channels": [...]}
    op.execute("ALTER TABLE intuition_models ADD COLUMN alert jsonb")
    op.execute("ALTER TABLE intuition_models ADD COLUMN last_alert_at timestamptz")

    op.execute("""CREATE TABLE rm_trace_task_types (
        trace_id uuid PRIMARY KEY REFERENCES rm_traces(id) ON DELETE CASCADE,
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        task_type text NOT NULL,
        assigned_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX rm_trace_task_types_owner ON rm_trace_task_types (owner_user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE rm_trace_task_types")
    op.execute("ALTER TABLE intuition_models DROP COLUMN last_alert_at")
    op.execute("ALTER TABLE intuition_models DROP COLUMN alert")
    op.execute("ALTER TABLE behavior_hits DROP COLUMN review_note")
    op.execute("ALTER TABLE behavior_alerts DROP COLUMN triage_id")
    op.execute("DROP TABLE behavior_triage")
    op.execute("DROP TABLE agent_releases")
