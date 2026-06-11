"""Add slack_user_links — map a Slack user to a Stash account.

The Slack agent maps an inbound mention/DM to the Stash user who connected
Slack, by the Slack user_id captured at connect time (email-independent). Part
of the removable Slack-agent feature.

Revision ID: 0096
Revises: 0095
"""

from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE slack_user_links (
            team_id       text NOT NULL,
            slack_user_id text NOT NULL,
            user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (team_id, slack_user_id)
        )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS slack_user_links")
