"""Multi-account integration tokens.

Revision ID: 0094
Revises: 0093
"""

from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_integrations ADD COLUMN account_key text")
    op.execute("""
        UPDATE user_integrations
        SET account_key = CASE
            WHEN provider = 'gmail' THEN lower(account_email)
            ELSE 'default'
        END
        """)
    op.execute("ALTER TABLE user_integrations ALTER COLUMN account_key SET NOT NULL")

    op.execute("""
        UPDATE workspace_sources ws
        SET external_ref = lower(ui.account_email),
            display_name = 'Gmail (' || lower(ui.account_email) || ')',
            updated_at = now()
        FROM user_integrations ui
        WHERE ws.owner_user_id = ui.user_id
          AND ws.source_type = 'gmail'
          AND ui.provider = 'gmail'
        """)

    op.execute("ALTER TABLE user_integrations DROP CONSTRAINT user_integrations_pkey")
    op.execute("""
        ALTER TABLE user_integrations
        ADD PRIMARY KEY (user_id, provider, account_key)
        """)
    op.execute(
        "CREATE INDEX user_integrations_user_provider_idx ON user_integrations (user_id, provider)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS user_integrations_user_provider_idx")
    op.execute("ALTER TABLE user_integrations DROP CONSTRAINT user_integrations_pkey")
    op.execute("""
        ALTER TABLE user_integrations
        ADD PRIMARY KEY (user_id, provider)
        """)
    op.execute("ALTER TABLE user_integrations DROP COLUMN account_key")
