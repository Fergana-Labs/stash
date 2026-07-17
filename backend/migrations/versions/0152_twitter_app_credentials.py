"""Per-user X (Twitter) developer-app OAuth credentials.

X gates the bookmarks API behind paid tiers, and reads count against the
app's quota — not the user's. So a user who wants server-side bookmark
sync (instead of the free extension capture) brings their own X app: we
run OAuth against their client id/secret, so their app bears the cost.
The secret is encrypted with the integration Fernet key.

Revision ID: 0148
Revises: 0147
"""

from alembic import op

revision = "0152"
down_revision = "0151"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE twitter_app_credentials (
            owner_user_id           uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            client_id               text NOT NULL,
            client_secret_encrypted bytea,
            created_at              timestamptz NOT NULL DEFAULT now(),
            updated_at              timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS twitter_app_credentials")
