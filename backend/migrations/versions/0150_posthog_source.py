"""PostHog project source index.

Revision ID: 0150
Revises: 0149
"""

from alembic import op

revision = "0150"
down_revision = "0149"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE posthog_index (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id           uuid NOT NULL REFERENCES user_sources(id) ON DELETE CASCADE,
            path                text NOT NULL,
            name                text NOT NULL,
            kind                text NOT NULL,
            external_ref        text NOT NULL,
            external_updated_at timestamptz,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            deleted_at          timestamptz,
            UNIQUE (source_id, path)
        )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS posthog_index")
