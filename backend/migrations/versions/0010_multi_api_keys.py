"""Multi-key auth: user_api_keys table, drop users.api_key_hash.

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS user_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL DEFAULT 'default',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
)
""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_user "
        "ON user_api_keys(user_id) WHERE revoked_at IS NULL"
    )

    # Backfill from users.api_key_hash — a user's current key keeps working.
    op.execute("""
INSERT INTO user_api_keys (user_id, key_hash, name)
SELECT id, api_key_hash, 'migrated'
FROM users
WHERE api_key_hash IS NOT NULL
ON CONFLICT (key_hash) DO NOTHING
""")

    op.execute("DROP INDEX IF EXISTS idx_users_api_key_hash")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS api_key_hash")


def downgrade() -> None:
    # Restore the column and repopulate from the newest surviving key per user.
    op.execute("ALTER TABLE users ADD COLUMN api_key_hash VARCHAR(64) UNIQUE")
    op.execute("""
UPDATE users u
SET api_key_hash = k.key_hash
FROM (
    SELECT DISTINCT ON (user_id) user_id, key_hash
    FROM user_api_keys
    WHERE revoked_at IS NULL
    ORDER BY user_id, created_at DESC
) k
WHERE u.id = k.user_id
""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_api_key_hash ON users(api_key_hash)")
    op.execute("DROP TABLE IF EXISTS user_api_keys CASCADE")
