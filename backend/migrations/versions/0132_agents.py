"""Named, configurable agents.

A user can create multiple agents, each with its own model (harness provider
override), persona (system prompt), run mode (interactive chat or a scheduled
headless run), and optional channel binding (which agent answers Slack /
Telegram). One default agent is created per user on demand.

Revision ID: 0132
Revises: 0131
"""

from alembic import op

revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agents (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name            text NOT NULL,
            model_provider  text,          -- null = auto-resolve; else anthropic|openai|openrouter
            system_prompt   text,          -- null = default persona; else appended
            run_mode        text NOT NULL DEFAULT 'chat',   -- 'chat' | 'scheduled'
            schedule_cron   text,          -- e.g. '0 9 * * *' when run_mode='scheduled'
            schedule_prompt text,          -- the instruction run on schedule
            is_default      boolean NOT NULL DEFAULT false,
            slack_bound     boolean NOT NULL DEFAULT false,
            telegram_bound  boolean NOT NULL DEFAULT false,
            last_run_at     timestamptz,
            created_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # One default / Slack / Telegram agent per user.
    op.execute(
        "CREATE UNIQUE INDEX one_default_agent_per_user ON agents (user_id) WHERE is_default"
    )
    op.execute(
        "CREATE UNIQUE INDEX one_slack_agent_per_user ON agents (user_id) WHERE slack_bound"
    )
    op.execute(
        "CREATE UNIQUE INDEX one_telegram_agent_per_user ON agents (user_id) WHERE telegram_bound"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agents")
