"""Connected sources can belong to an org.

External Multiplayer says an org is "its own pile of files and sessions", and
that "files can be added from a number of integrations, including Google
Drive". Sessions and uploaded files already carry `org_id`; connected sources
did not, so a developer could not attach a customer's Drive folder to that
customer — their org's VFS view listed no sources at all.

A NULL `org_id` is the developer's own source, shared across the workspace as
before. A set `org_id` scopes the source to one customer: only that org's
reads see it.

Revision ID: 0190
Revises: 0189
"""

from alembic import op

revision = "0190"
down_revision = "0189"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_sources ADD COLUMN org_id UUID REFERENCES orgs(id) ON DELETE CASCADE"
    )
    op.execute(
        "CREATE INDEX idx_user_sources_org ON user_sources (org_id) WHERE org_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_sources_org")
    op.execute("ALTER TABLE user_sources DROP COLUMN IF EXISTS org_id")
