"""Record the scope set an embedding projection was computed over.

The knowledge-map projection now computes in the Celery worker and the
endpoint serves from this cache. A user-wide cache row mixes content from
every scope the user could read at compute time, so serving it after an
access change would leak points from revoked scopes. The read path compares
the stored scope set against the caller's current one and treats any
mismatch as a cache miss.

Revision ID: 0143
Revises: 0142
"""

from alembic import op

revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE embedding_projections ADD COLUMN scope_ids UUID[] NOT NULL DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE embedding_projections DROP COLUMN scope_ids")
