"""Store publish state on Product Stashes.

Revision ID: 0052
Revises: 0051
"""

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stashes ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute("""
UPDATE stashes s
SET is_public = true
FROM object_permissions op
WHERE op.object_type = 'stash'
  AND op.object_id = s.id
  AND op.visibility = 'public'
""")
    op.execute("DROP TABLE IF EXISTS object_shares CASCADE")
    op.execute("DROP TABLE IF EXISTS object_permissions CASCADE")


def downgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS object_permissions (
    object_type VARCHAR(32) NOT NULL,
    object_id UUID NOT NULL,
    visibility VARCHAR(16) NOT NULL DEFAULT 'inherit'
        CHECK(visibility IN ('inherit', 'private', 'link', 'public')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (object_type, object_id)
)
""")
    op.execute("""
CREATE TABLE IF NOT EXISTS object_shares (
    object_type VARCHAR(32) NOT NULL,
    object_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission VARCHAR(16) NOT NULL DEFAULT 'read',
    granted_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (object_type, object_id, user_id)
)
""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_object_shares_user ON object_shares(user_id)")
    op.execute("""
INSERT INTO object_permissions (object_type, object_id, visibility)
SELECT 'stash', id, 'public'
FROM stashes
WHERE is_public = true
ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = 'public'
""")
    op.execute("ALTER TABLE stashes DROP COLUMN IF EXISTS is_public")
