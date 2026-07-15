"""Replace legacy PostHog API-key connections with OAuth.

Revision ID: 0151
Revises: 0150
"""

from alembic import op

revision = "0151"
down_revision = "0150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM user_sources
        WHERE source_type = 'posthog'
          AND owner_user_id IN (
              SELECT user_id FROM user_integrations
              WHERE provider = 'posthog' AND client_info IS NULL
          )
        """)
    op.execute("""
        DELETE FROM user_integrations
        WHERE provider = 'posthog' AND client_info IS NULL
        """)


def downgrade() -> None:
    pass
