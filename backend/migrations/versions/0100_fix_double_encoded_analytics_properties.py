"""Repair double-encoded analytics_events.properties.

analytics_events_service json.dumps'd properties while the asyncpg pool's
jsonb codec serialized them again, so every row's properties was stored as
a JSON *string* containing JSON ('"{\\"k\\": 1}"' instead of '{"k": 1}'),
which makes properties->>'k' return NULL. Unwrap the string rows in place.

Revision ID: 0100
Revises: 0099
Create Date: 2026-06-10
"""

from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE analytics_events
        SET properties = (properties #>> '{}')::jsonb
        WHERE jsonb_typeof(properties) = 'string'
        """)


def downgrade() -> None:
    pass
