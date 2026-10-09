"""Owner-scoped names for stable trace source IDs.

Revision ID: 0232
Revises: 0231
"""

from alembic import op

revision = "0232"
down_revision = "0231"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE rm_trace_sources (
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source_id text NOT NULL CHECK (length(btrim(source_id)) BETWEEN 1 AND 200),
        name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
        PRIMARY KEY (owner_user_id, source_id)
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE rm_trace_sources")
