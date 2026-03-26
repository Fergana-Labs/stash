import asyncpg
from .config import settings

pool: asyncpg.Pool | None = None

SCHEMA = """
-- Users (unchanged from before, plus owner_id for agent identities)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(128),
    type VARCHAR(8) NOT NULL CHECK(type IN ('human', 'agent')),
    api_key_hash VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(72),
    description TEXT DEFAULT '',
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Workspaces (top-level container)
CREATE TABLE IF NOT EXISTS workspaces (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(128) NOT NULL,
    description TEXT DEFAULT '',
    creator_id  UUID NOT NULL REFERENCES users(id),
    invite_code VARCHAR(12) NOT NULL UNIQUE,
    is_public   BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         VARCHAR(8) NOT NULL DEFAULT 'member'
                 CHECK(role IN ('owner', 'admin', 'member')),
    joined_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
);

-- Chats (messaging within workspaces, or DMs without workspace)
CREATE TABLE IF NOT EXISTS chats (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name         VARCHAR(128) NOT NULL,
    description  TEXT DEFAULT '',
    creator_id   UUID NOT NULL REFERENCES users(id),
    is_dm        BOOLEAN NOT NULL DEFAULT false,
    dm_user_a    UUID REFERENCES users(id),
    dm_user_b    UUID REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_dm_users CHECK (
        NOT is_dm OR (dm_user_a IS NOT NULL AND dm_user_b IS NOT NULL AND dm_user_a < dm_user_b)
    )
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id      UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    sender_id    UUID NOT NULL REFERENCES users(id),
    content      TEXT NOT NULL,
    message_type VARCHAR(8) DEFAULT 'text' CHECK(message_type IN ('text', 'system')),
    reply_to_id  UUID REFERENCES chat_messages(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Notebook folders (must be created before notebooks for FK)
CREATE TABLE IF NOT EXISTS notebook_folders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         VARCHAR(255) NOT NULL,
    created_by   UUID NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, name)
);

-- Notebooks (markdown files with collaborative editing)
CREATE TABLE IF NOT EXISTS notebooks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    folder_id        UUID REFERENCES notebook_folders(id) ON DELETE SET NULL,
    name             VARCHAR(255) NOT NULL,
    content_markdown TEXT NOT NULL DEFAULT '',
    yjs_state        BYTEA,
    created_by       UUID NOT NULL REFERENCES users(id),
    updated_by       UUID REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Memory stores (containers for structured agent events)
CREATE TABLE IF NOT EXISTS memory_stores (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         VARCHAR(128) NOT NULL,
    description  TEXT DEFAULT '',
    created_by   UUID NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, name)
);

-- Memory events (append-only structured records)
CREATE TABLE IF NOT EXISTS memory_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id     UUID NOT NULL REFERENCES memory_stores(id) ON DELETE CASCADE,
    agent_name   VARCHAR(64) NOT NULL,
    event_type   VARCHAR(64) NOT NULL,
    session_id   VARCHAR(64),
    tool_name    VARCHAR(128),
    content      TEXT NOT NULL,
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Object permissions (Google Drive-like, shared across all object types)
CREATE TABLE IF NOT EXISTS object_permissions (
    object_type  VARCHAR(16) NOT NULL CHECK(object_type IN ('chat', 'notebook', 'memory_store')),
    object_id    UUID NOT NULL,
    visibility   VARCHAR(16) NOT NULL DEFAULT 'inherit'
                 CHECK(visibility IN ('inherit', 'private', 'public')),
    PRIMARY KEY (object_type, object_id)
);

CREATE TABLE IF NOT EXISTS object_shares (
    object_type  VARCHAR(16) NOT NULL CHECK(object_type IN ('chat', 'notebook', 'memory_store')),
    object_id    UUID NOT NULL,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission   VARCHAR(8) NOT NULL DEFAULT 'read'
                 CHECK(permission IN ('read', 'write', 'admin')),
    granted_by   UUID NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (object_type, object_id, user_id)
);

-- Webhooks (per-workspace, one per user per workspace)
CREATE TABLE IF NOT EXISTS webhooks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url          TEXT NOT NULL,
    secret       VARCHAR(128),
    event_filter TEXT[] DEFAULT '{}',
    is_active    BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, user_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_api_key_hash ON users(api_key_hash);
CREATE INDEX IF NOT EXISTS idx_users_owner ON users(owner_id) WHERE owner_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_workspaces_invite_code ON workspaces(invite_code);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id);

CREATE INDEX IF NOT EXISTS idx_chats_workspace ON chats(workspace_id) WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_created ON chat_messages(chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_fts ON chat_messages USING GIN(to_tsvector('english', content));

CREATE INDEX IF NOT EXISTS idx_notebooks_workspace ON notebooks(workspace_id);
CREATE INDEX IF NOT EXISTS idx_notebooks_folder ON notebooks(folder_id);

CREATE INDEX IF NOT EXISTS idx_memory_stores_workspace ON memory_stores(workspace_id);
CREATE INDEX IF NOT EXISTS idx_memory_events_store_created ON memory_events(store_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_events_agent ON memory_events(store_id, agent_name);
CREATE INDEX IF NOT EXISTS idx_memory_events_session ON memory_events(store_id, session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_memory_events_type ON memory_events(store_id, event_type);
CREATE INDEX IF NOT EXISTS idx_memory_events_fts ON memory_events USING GIN(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_memory_events_metadata ON memory_events USING GIN(metadata);

CREATE INDEX IF NOT EXISTS idx_object_shares_user ON object_shares(user_id);
CREATE INDEX IF NOT EXISTS idx_webhooks_workspace ON webhooks(workspace_id) WHERE is_active = true;
"""

# Partial unique indexes (need separate execution due to WHERE clause)
_PARTIAL_INDEXES = [
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_dm_unique_pair
       ON chats(dm_user_a, dm_user_b) WHERE is_dm = true""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_notebooks_root_unique
       ON notebooks(workspace_id, name) WHERE folder_id IS NULL""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_notebooks_folder_unique
       ON notebooks(workspace_id, folder_id, name) WHERE folder_id IS NOT NULL""",
]


async def init_db():
    global pool
    pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
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
