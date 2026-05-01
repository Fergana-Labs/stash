"""Persist CLI auth sessions in the database instead of in-memory dict.

Revision ID: 0024
Revises: 0023
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS cli_auth_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    device_name VARCHAR(128) NOT NULL DEFAULT '',
    api_key TEXT,
    username VARCHAR(256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cli_auth_sessions")
