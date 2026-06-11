"""Add onboarding profile fields to users — role, referral_source, use_case.

Captured in the first onboarding step so we know who's signing up, how they
found us, and what they want to build. Nullable: older accounts never answered.

Revision ID: 0097
Revises: 0096
"""

from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
            ADD COLUMN role            text,
            ADD COLUMN referral_source text,
            ADD COLUMN use_case        text
        """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE users
            DROP COLUMN IF EXISTS role,
            DROP COLUMN IF EXISTS referral_source,
            DROP COLUMN IF EXISTS use_case
        """)
