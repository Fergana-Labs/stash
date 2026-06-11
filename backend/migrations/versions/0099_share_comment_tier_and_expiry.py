"""Sharing: a 'comment' permission tier + expiring links.

`permission` gains a middle level (read < comment < write), pinned by a CHECK
constraint. `expires_at` lets a share/invite auto-lapse; NULL means it never
expires. Existing rows are read/write, already valid; nothing to backfill.

Revision ID: 0099
Revises: 0098
"""

from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE shares ADD COLUMN expires_at timestamptz")
    op.execute("ALTER TABLE share_invites ADD COLUMN expires_at timestamptz")
    op.execute(
        "ALTER TABLE shares ADD CONSTRAINT shares_permission_chk "
        "CHECK (permission IN ('read', 'comment', 'write'))"
    )
    op.execute(
        "ALTER TABLE share_invites ADD CONSTRAINT share_invites_permission_chk "
        "CHECK (permission IN ('read', 'comment', 'write'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE shares DROP CONSTRAINT IF EXISTS shares_permission_chk")
    op.execute("ALTER TABLE share_invites DROP CONSTRAINT IF EXISTS share_invites_permission_chk")
    op.execute("ALTER TABLE shares DROP COLUMN IF EXISTS expires_at")
    op.execute("ALTER TABLE share_invites DROP COLUMN IF EXISTS expires_at")
