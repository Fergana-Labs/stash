import asyncpg
from .config import settings

pool: asyncpg.Pool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(128),
    type VARCHAR(8) NOT NULL CHECK(type IN ('human', 'agent')),
    api_key_hash VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(72),
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    description TEXT DEFAULT '',
    creator_id UUID NOT NULL REFERENCES users(id),
    invite_code VARCHAR(12) NOT NULL UNIQUE,
    is_public BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS room_members (
    room_id UUID REFERENCES rooms(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(8) DEFAULT 'member' CHECK(role IN ('owner', 'admin', 'member')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (room_id, user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    message_type VARCHAR(8) DEFAULT 'text' CHECK(message_type IN ('text', 'system')),
    reply_to_id UUID REFERENCES messages(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS room_access_list (
    room_id    UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    user_name  VARCHAR(64) NOT NULL,
    list_type  VARCHAR(5) NOT NULL CHECK(list_type IN ('allow', 'block')),
    added_by   UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (room_id, user_name, list_type)
);

CREATE TABLE IF NOT EXISTS webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    secret VARCHAR(128),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_room_created ON messages(room_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_content_fts ON messages USING GIN(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_rooms_invite_code ON rooms(invite_code);
CREATE INDEX IF NOT EXISTS idx_users_api_key_hash ON users(api_key_hash);
"""

# Idempotent column/table additions for existing databases
MIGRATIONS = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(72);
ALTER TABLE users ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS type VARCHAR(12) DEFAULT 'chat';

CREATE TABLE IF NOT EXISTS workspace_folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, name)
);

CREATE TABLE IF NOT EXISTS workspace_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    folder_id UUID REFERENCES workspace_folders(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    content_markdown TEXT NOT NULL DEFAULT '',
    yjs_state BYTEA,
    created_by UUID NOT NULL REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workspace_files_workspace ON workspace_files(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_files_folder ON workspace_files(folder_id);
"""

# Partial unique indexes (need separate execution due to WHERE clause)
_PARTIAL_INDEXES = [
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_files_root_unique
       ON workspace_files(workspace_id, name) WHERE folder_id IS NULL""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_files_folder_unique
       ON workspace_files(workspace_id, folder_id, name) WHERE folder_id IS NOT NULL""",
]


async def init_db():
    global pool
    pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
        await conn.execute(MIGRATIONS)
        for idx_sql in _PARTIAL_INDEXES:
            await conn.execute(idx_sql)


async def close_db():
    global pool
    if pool:
        await pool.close()
        pool = None


def get_pool() -> asyncpg.Pool:
    assert pool is not None, "Database not initialized"
    return pool
