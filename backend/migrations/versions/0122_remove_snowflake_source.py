"""Remove the Snowflake source.

The Snowflake integration is gone (no provider, no queryable capability), so any
rows left behind would 500 on list_sources when their source_type no longer maps
to a provider. Drop the connected sources and their stored credentials in one
shot. Their per-source documents cascade — queryable sources never had a
document table, so there is nothing else to clean up.

Revision ID: 0122
Revises: 0121
"""

from alembic import op

revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM user_sources WHERE source_type = 'snowflake'")
    op.execute("DELETE FROM user_integrations WHERE provider = 'snowflake'")


def downgrade() -> None:
    # The rows are gone; a downgrade cannot resurrect the deleted credentials.
    pass
