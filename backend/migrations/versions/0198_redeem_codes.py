"""Redeemable access codes (hackathons).

A code grants a plan: redeeming sets `users.plan` — the same entitlement the
admin plan endpoint grants ('enterprise' = unlimited sleep-time curator runs).
`users.redeemed_code` records which code an account came in through, so a
hackathon cohort stays queryable, and blocks double redemption.

Revision ID: 0198
Revises: 0197
"""

from alembic import op

revision = "0198"
down_revision = "0197"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE redeem_codes (
            code text PRIMARY KEY,
            plan text NOT NULL,
            max_uses integer,
            use_count integer NOT NULL DEFAULT 0,
            expires_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE users ADD COLUMN redeemed_code text REFERENCES redeem_codes(code)")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS redeemed_code")
    op.execute("DROP TABLE IF EXISTS redeem_codes")
