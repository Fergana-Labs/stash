"""Add slack_bot_installs — team bot tokens for the Slack agent.

The Slack agent (talk-to-Stash bot) posts replies with a team-scoped bot
token, captured during OAuth alongside the existing user token. One row per
Slack team. This whole table belongs to the removable Slack-agent feature.

Revision ID: 0094
Revises: 0093
"""

from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE slack_bot_installs (
            team_id              text PRIMARY KEY,
            bot_token_encrypted  bytea NOT NULL,
            bot_user_id          text,
            installed_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            updated_at           timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS slack_bot_installs")
