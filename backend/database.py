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

CREATE INDEX IF NOT EXISTS idx_messages_room_created ON messages(room_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_content_fts ON messages USING GIN(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_rooms_invite_code ON rooms(invite_code);
CREATE INDEX IF NOT EXISTS idx_users_api_key_hash ON users(api_key_hash);
"""


async def init_db():
    global pool
    pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)


async def close_db():
    global pool
    if pool:
        await pool.close()
        pool = None


def get_pool() -> asyncpg.Pool:
    assert pool is not None, "Database not initialized"
    return pool
