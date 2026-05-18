"""Make Stashes the privacy boundary.

Revision ID: 0053
Revises: 0052
"""

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE stashes
ADD COLUMN IF NOT EXISTS access VARCHAR(16) NOT NULL DEFAULT 'workspace'
""")
    op.execute("""
UPDATE stashes
SET access = CASE WHEN is_public THEN 'public' ELSE 'workspace' END
""")
    op.execute("""
ALTER TABLE stashes
DROP CONSTRAINT IF EXISTS stashes_access_check
""")
    op.execute("""
ALTER TABLE stashes
ADD CONSTRAINT stashes_access_check CHECK (access IN ('workspace', 'private', 'public'))
""")
    op.execute("ALTER TABLE stashes DROP COLUMN IF EXISTS is_public")
    op.execute("""
CREATE TABLE IF NOT EXISTS stash_members (
    stash_id UUID NOT NULL REFERENCES stashes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission VARCHAR(16) NOT NULL DEFAULT 'read'
        CHECK(permission IN ('read', 'write', 'admin')),
    granted_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (stash_id, user_id)
)
""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stash_members_user ON stash_members(user_id)")
    op.execute("DROP TABLE IF EXISTS privacy_tag_objects CASCADE")
    op.execute("DROP TABLE IF EXISTS privacy_tag_members CASCADE")
    op.execute("DROP TABLE IF EXISTS privacy_tags CASCADE")
    op.execute("DROP TABLE IF EXISTS page_links CASCADE")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE stashes ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute("UPDATE stashes SET is_public = access = 'public'")
    op.execute("DROP TABLE IF EXISTS stash_members CASCADE")
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_access_check")
    op.execute("ALTER TABLE stashes DROP COLUMN IF EXISTS access")
