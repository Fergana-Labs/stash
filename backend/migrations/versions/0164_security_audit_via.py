"""Add via (caller surface) to security_audit_events.

Tags every audit row with how the request arrived — 'web' (browser JWT or
anonymous), 'cli' (API key), or 'ask' (ask-the-stash's nested VFS reads) — so
the admin content-activity dashboard can split reads/searches/listings by
source. Pre-existing rows stay NULL and are excluded from per-surface stats.
"""

from alembic import op

revision = "0164"
down_revision = "0163"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE security_audit_events ADD COLUMN via text")


def downgrade() -> None:
    op.execute("ALTER TABLE security_audit_events DROP COLUMN via")
