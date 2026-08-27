"""Record which API key uploaded each history event.

Revision ID: 0209
Revises: 0208
"""

from alembic import op

revision = "0209"
down_revision = "0208"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_api_keys ADD COLUMN uploads_enabled BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute(
        "ALTER TABLE history_events ADD COLUMN uploader_key_id UUID "
        "REFERENCES user_api_keys(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX idx_history_events_uploader_key "
        "ON history_events(owner_user_id, uploader_key_id) "
        "WHERE uploader_key_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_history_events_uploader_key")
    op.execute("ALTER TABLE history_events DROP COLUMN uploader_key_id")
    op.execute("ALTER TABLE user_api_keys DROP COLUMN uploads_enabled")
