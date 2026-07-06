"""User plan entitlement and curator run metering.

`plan` is the billing entitlement ('free' | 'enterprise') — enterprise means
unlimited sleep-time curator runs; free accounts get a monthly allowance.
`plan_intent` is what the user picked during onboarding (a sales signal, not
an entitlement). `month_run_count`/`month_run_anchor` meter scheduled-agent
runs per calendar month for the free-tier curator gate.

Revision ID: 0135
Revises: 0134
"""

from alembic import op

revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN plan text NOT NULL DEFAULT 'free'")
    op.execute("ALTER TABLE users ADD COLUMN plan_intent text")
    op.execute("ALTER TABLE agents ADD COLUMN month_run_count integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE agents ADD COLUMN month_run_anchor date")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS plan")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS plan_intent")
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS month_run_count")
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS month_run_anchor")
