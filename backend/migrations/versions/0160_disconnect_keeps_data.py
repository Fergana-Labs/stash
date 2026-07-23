"""Disconnect keeps data: provider account identity + nullable tokens.

Disconnecting an integration now keeps the user_integrations row with its
tokens nulled, so the provider-account identity survives disconnect and a
later reconnect can be verified against it. account_ref is the provider's
stable account id (X user id, Google email, GitHub login), recorded at
connect; the mismatch check refuses a reconnect under a different account
while kept data exists.

Backfilled where the id already lives on our side — X from the x_saves
source external_ref, Gmail from its per-email account_key — so those are
protected immediately; other providers record it at their next connect.

Revision ID: 0160
Revises: 0159
"""

from alembic import op

revision = "0160"
down_revision = "0159"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_integrations ADD COLUMN account_ref text")
    op.execute("ALTER TABLE user_integrations ALTER COLUMN access_token_encrypted DROP NOT NULL")
    op.execute("""
        UPDATE user_integrations ui
        SET account_ref = us.external_ref
        FROM user_sources us
        WHERE ui.provider = 'x'
          AND ui.account_ref IS NULL
          AND us.owner_user_id = ui.user_id
          AND us.source_type = 'x_saves'
        """)
    op.execute(
        "UPDATE user_integrations SET account_ref = account_key "
        "WHERE provider = 'gmail' AND account_ref IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE user_integrations DROP COLUMN IF EXISTS account_ref")
