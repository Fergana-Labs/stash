"""Drop the session Linear-ticket feature's tables.

The session ↔ Linear ticket association (regex extraction from transcripts,
GitHub-PR-based discovery, API enrichment) is removed from the product, so
its two tables go with it. The Linear connected source (/sources) is a
separate feature and keeps its own tables.

Revision ID: 0203
Revises: 0202
"""

from alembic import op

revision = "0203"
down_revision = "0202"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_linear_tickets CASCADE")
    op.execute("DROP TABLE IF EXISTS session_github_pull_requests CASCADE")


def downgrade() -> None:
    raise NotImplementedError("The extracted ticket labels are not recoverable.")
