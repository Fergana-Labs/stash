"""Telegram agent — link a Telegram user to a Stash account.

A single platform bot (TELEGRAM_BOT_TOKEN) serves every user, so there's no
per-team install table like Slack's. Identity is a deep-link connect: the user
opens t.me/<bot>?start=<code> with a short-lived code minted in settings, and
the bot's /start handler binds their Telegram id to their account.

Revision ID: 0124
Revises: 0123
"""

from alembic import op

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE telegram_user_links (
            telegram_user_id text PRIMARY KEY,
            user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at       timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE telegram_connect_codes (
            code       text PRIMARY KEY,
            user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS telegram_connect_codes")
    op.execute("DROP TABLE IF EXISTS telegram_user_links")
