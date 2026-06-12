"""Per-user Stripe subscription state for the Pro plan pay gate.

Revision ID: 0111
Revises: 0110
"""

from alembic import op

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per user, created the first time they start checkout. Status
    # mirrors Stripe's subscription status vocabulary (no CHECK — Stripe owns
    # it). The UNIQUE on stripe_customer_id is the webhook lookup index.
    op.execute("""
        CREATE TABLE user_subscriptions (
            user_id                uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            stripe_customer_id     text NOT NULL UNIQUE,
            stripe_subscription_id text,
            status                 text NOT NULL DEFAULT 'incomplete',
            created_at             timestamptz NOT NULL DEFAULT now(),
            updated_at             timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_subscriptions")
