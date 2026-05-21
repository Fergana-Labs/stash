"""Product telemetry table — usage events from onboarding, web actions, and the stash CLI.

Distinct from history_events (which is the agent-transcript log, embedded and content-heavy).
analytics_events stays small: structured properties JSONB, no content/embedding.

Revision ID: 0074
Revises: 0073
Create Date: 2026-05-20
"""

from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS analytics_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    surface VARCHAR(16) NOT NULL,
    event_name VARCHAR(64) NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}',
    session_anon VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS analytics_events_user_idx "
        "ON analytics_events(user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS analytics_events_event_name_idx "
        "ON analytics_events(event_name, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS analytics_events_surface_idx "
        "ON analytics_events(surface, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analytics_events")
