import json

import asyncpg
from pgvector.asyncpg import register_vector

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
    notebook_id UUID,   -- agent-owned notebook (set after notebook creation)
    history_id UUID,    -- agent-owned history (set after history creation)
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

-- Chat watches (agent notification subscriptions)
CREATE TABLE IF NOT EXISTS chat_watches (
    agent_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id      UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    last_read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_id, chat_id)
);

-- Notebooks (collections of folders + pages)
CREATE TABLE IF NOT EXISTS notebooks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name         VARCHAR(255) NOT NULL,
    description  TEXT DEFAULT '',
    created_by   UUID NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Notebook folders (within a notebook)
CREATE TABLE IF NOT EXISTS notebook_folders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notebook_id  UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    name         VARCHAR(255) NOT NULL,
    created_by   UUID NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(notebook_id, name)
);

-- Notebook pages (markdown files within a notebook)
CREATE TABLE IF NOT EXISTS notebook_pages (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notebook_id      UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    folder_id        UUID REFERENCES notebook_folders(id) ON DELETE SET NULL,
    name             VARCHAR(255) NOT NULL,
    content_markdown TEXT NOT NULL DEFAULT '',
    content_hash     VARCHAR(64),
    metadata         JSONB DEFAULT '{}',
    yjs_state        BYTEA,
    created_by       UUID NOT NULL REFERENCES users(id),
    updated_by       UUID REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Histories (containers for structured agent events)
CREATE TABLE IF NOT EXISTS histories (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name         VARCHAR(128) NOT NULL,
    description  TEXT DEFAULT '',
    created_by   UUID NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, name)
);

-- History events (append-only structured records)
CREATE TABLE IF NOT EXISTS history_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id     UUID NOT NULL REFERENCES histories(id) ON DELETE CASCADE,
    agent_name   VARCHAR(64) NOT NULL,
    event_type   VARCHAR(64) NOT NULL,
    session_id   VARCHAR(64),
    tool_name    VARCHAR(128),
    content      TEXT NOT NULL,
    metadata     JSONB DEFAULT '{}',
    embedding    vector(384),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Injection configs (per-agent scoring parameters)
CREATE TABLE IF NOT EXISTS injection_configs (
    agent_id     UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    budget_tokens INTEGER NOT NULL DEFAULT 4000,
    min_score    REAL NOT NULL DEFAULT 0.01,
    recency_intervals REAL[] NOT NULL DEFAULT '{1.0,4.0,24.0,72.0,168.0,720.0}',
    staleness_decay_fast  REAL NOT NULL DEFAULT 0.15,
    staleness_decay_slow  REAL NOT NULL DEFAULT 0.40,
    staleness_fast_threshold_seconds REAL NOT NULL DEFAULT 60.0,
    embedding_dims INTEGER NOT NULL DEFAULT 384,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sleep watermarks (per-agent curation progress)
CREATE TABLE IF NOT EXISTS sleep_watermarks (
    agent_id              UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    last_event_at         TIMESTAMPTZ,
    last_monologue_event_at TIMESTAMPTZ,
    last_run_at           TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Injection sessions (server-side injection state for outcome scoring)
CREATE TABLE IF NOT EXISTS injection_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id      VARCHAR(64) NOT NULL,
    injected_items  JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    scored_at       TIMESTAMPTZ,
    UNIQUE(agent_id, session_id)
);

-- Sleep configs (per-agent curation settings)
CREATE TABLE IF NOT EXISTS sleep_configs (
    agent_id              UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    enabled               BOOLEAN NOT NULL DEFAULT true,
    interval_minutes      INTEGER NOT NULL DEFAULT 60,
    max_pattern_cards     INTEGER NOT NULL DEFAULT 500,
    monologue_batch_size  INTEGER NOT NULL DEFAULT 20,
    monologue_model       VARCHAR(64) NOT NULL DEFAULT 'claude-haiku-4-5-20251001',
    curation_model        VARCHAR(64) NOT NULL DEFAULT 'claude-sonnet-4-6-20250514',
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Decks (HTML/JS/CSS documents)
CREATE TABLE IF NOT EXISTS decks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name         VARCHAR(255) NOT NULL,
    description  TEXT DEFAULT '',
    html_content TEXT NOT NULL DEFAULT '',
    deck_type    VARCHAR(32) DEFAULT 'freeform'
                 CHECK(deck_type IN ('freeform', 'slides', 'dashboard')),
    created_by   UUID NOT NULL REFERENCES users(id),
    updated_by   UUID REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Deck share links (public token-based access)
CREATE TABLE IF NOT EXISTS deck_shares (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id         UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    token           VARCHAR(16) NOT NULL UNIQUE,
    name            VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    require_email   BOOLEAN NOT NULL DEFAULT false,
    passcode_hash   VARCHAR(72),
    allow_download  BOOLEAN NOT NULL DEFAULT true,
    expires_at      TIMESTAMPTZ,
    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Deck share views (viewer session tracking)
CREATE TABLE IF NOT EXISTS deck_share_views (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    share_id              UUID NOT NULL REFERENCES deck_shares(id) ON DELETE CASCADE,
    session_token         VARCHAR(96) NOT NULL UNIQUE,
    viewer_email          VARCHAR(255),
    viewer_ip             VARCHAR(45),
    user_agent            TEXT,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_duration_seconds INTEGER NOT NULL DEFAULT 0
);

-- Deck share page views (per-page engagement)
CREATE TABLE IF NOT EXISTS deck_share_page_views (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    view_id           UUID NOT NULL REFERENCES deck_share_views(id) ON DELETE CASCADE,
    page_identifier   VARCHAR(255) NOT NULL,
    entered_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_seconds  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(view_id, page_identifier)
);

-- Object permissions (Google Drive-like, shared across all object types)
CREATE TABLE IF NOT EXISTS object_permissions (
    object_type  VARCHAR(16) NOT NULL CHECK(object_type IN ('chat', 'notebook', 'history', 'deck')),
    object_id    UUID NOT NULL,
    visibility   VARCHAR(16) NOT NULL DEFAULT 'inherit'
                 CHECK(visibility IN ('inherit', 'private', 'public')),
    PRIMARY KEY (object_type, object_id)
);

CREATE TABLE IF NOT EXISTS object_shares (
    object_type  VARCHAR(16) NOT NULL CHECK(object_type IN ('chat', 'notebook', 'history', 'deck')),
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

CREATE INDEX IF NOT EXISTS idx_chat_watches_agent ON chat_watches(agent_id) WHERE enabled = true;

CREATE INDEX IF NOT EXISTS idx_notebooks_workspace ON notebooks(workspace_id);
CREATE INDEX IF NOT EXISTS idx_notebook_pages_notebook ON notebook_pages(notebook_id);
CREATE INDEX IF NOT EXISTS idx_notebook_pages_folder ON notebook_pages(folder_id);
CREATE INDEX IF NOT EXISTS idx_notebook_folders_notebook ON notebook_folders(notebook_id);

CREATE INDEX IF NOT EXISTS idx_histories_workspace ON histories(workspace_id);
CREATE INDEX IF NOT EXISTS idx_history_events_store_created ON history_events(store_id, created_at);
CREATE INDEX IF NOT EXISTS idx_history_events_agent ON history_events(store_id, agent_name);
CREATE INDEX IF NOT EXISTS idx_history_events_session ON history_events(store_id, session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_history_events_type ON history_events(store_id, event_type);
CREATE INDEX IF NOT EXISTS idx_history_events_fts ON history_events USING GIN(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_history_events_metadata ON history_events USING GIN(metadata);

CREATE INDEX IF NOT EXISTS idx_notebook_pages_fts ON notebook_pages USING GIN(to_tsvector('english', content_markdown));

CREATE INDEX IF NOT EXISTS idx_injection_sessions_agent ON injection_sessions(agent_id);

CREATE INDEX IF NOT EXISTS idx_decks_workspace ON decks(workspace_id);
CREATE INDEX IF NOT EXISTS idx_deck_shares_deck ON deck_shares(deck_id);
CREATE INDEX IF NOT EXISTS idx_deck_shares_token ON deck_shares(token);
CREATE INDEX IF NOT EXISTS idx_deck_share_views_share ON deck_share_views(share_id);
CREATE INDEX IF NOT EXISTS idx_deck_share_views_session ON deck_share_views(session_token);
CREATE INDEX IF NOT EXISTS idx_deck_share_page_views_view ON deck_share_page_views(view_id);

CREATE INDEX IF NOT EXISTS idx_object_shares_user ON object_shares(user_id);
CREATE INDEX IF NOT EXISTS idx_webhooks_workspace ON webhooks(workspace_id) WHERE is_active = true;
"""

# Partial unique indexes (need separate execution due to WHERE clause)
_PARTIAL_INDEXES = [
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_dm_unique_pair
       ON chats(dm_user_a, dm_user_b) WHERE is_dm = true""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_notebook_pages_root_unique
       ON notebook_pages(notebook_id, name) WHERE folder_id IS NULL""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_notebook_pages_folder_unique
       ON notebook_pages(notebook_id, folder_id, name) WHERE folder_id IS NOT NULL""",
    # Personal (workspace-less) item uniqueness — scoped to created_by
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_history_unique
       ON histories(created_by, name) WHERE workspace_id IS NULL""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_notebook_unique
       ON notebooks(created_by, name) WHERE workspace_id IS NULL""",
    # Personal item query indexes
    """CREATE INDEX IF NOT EXISTS idx_notebooks_personal
       ON notebooks(created_by) WHERE workspace_id IS NULL""",
    """CREATE INDEX IF NOT EXISTS idx_histories_personal
       ON histories(created_by) WHERE workspace_id IS NULL""",
    """CREATE INDEX IF NOT EXISTS idx_chats_personal
       ON chats(creator_id) WHERE workspace_id IS NULL AND is_dm = false""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_deck_unique
       ON decks(created_by, name) WHERE workspace_id IS NULL""",
    """CREATE INDEX IF NOT EXISTS idx_decks_personal
       ON decks(created_by) WHERE workspace_id IS NULL""",
    # Injection sessions pending outcome scoring
    """CREATE INDEX IF NOT EXISTS idx_injection_sessions_pending
       ON injection_sessions(agent_id) WHERE completed_at IS NOT NULL AND scored_at IS NULL""",
    # pgvector HNSW index for semantic search on history events
    """CREATE INDEX IF NOT EXISTS idx_history_events_embedding
       ON history_events USING hnsw (embedding vector_cosine_ops)
       WHERE embedding IS NOT NULL""",
]


async def init_db():
    global pool

    # First, ensure pgvector extension exists before creating the pool,
    # because the pool's init callback registers the vector type codec
    # on every new connection (which fails if the extension isn't installed).
    bootstrap = await asyncpg.connect(settings.DATABASE_URL)
    try:
        await bootstrap.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await bootstrap.close()

    async def _init_connection(conn):
        await register_vector(conn)
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )
        await conn.set_type_codec(
            "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    pool = await asyncpg.create_pool(
        settings.DATABASE_URL, min_size=2, max_size=10, init=_init_connection,
    )
    async with pool.acquire() as conn:
        # Check if schema needs a full reset (old incompatible schema detection)
        has_workspaces = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'workspaces'"
        )
        if not has_workspaces:
            # Old schema without workspaces — drop everything and recreate
            await conn.execute("""
                DROP TABLE IF EXISTS
                    webhooks, object_shares, object_permissions,
                    history_events, histories, memory_events, memory_stores,
                    notebook_pages, notebook_folders, notebooks,
                    chat_messages, chats,
                    workspace_members, workspaces,
                    users
                CASCADE
            """)
        else:
            # Migration: restructure notebooks (old schema had notebooks as files)
            has_notebook_pages = await conn.fetchval(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'notebook_pages'"
            )
            if not has_notebook_pages:
                # Old schema — drop old notebook tables, new schema will recreate
                await conn.execute("""
                    DROP TABLE IF EXISTS notebook_folders, notebooks CASCADE
                """)

            # Migration: rename memory_stores → histories if needed
            for old, new in [("memory_stores", "histories"), ("memory_events", "history_events")]:
                old_exists = await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = $1", old,
                )
                new_exists = await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = $1", new,
                )
                if old_exists and not new_exists:
                    await conn.execute(f"ALTER TABLE {old} RENAME TO {new}")
            # Migration: update object_type values and CHECK constraints
            for tbl_name in ("object_permissions", "object_shares"):
                tbl_exists = await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = $1", tbl_name,
                )
                if tbl_exists:
                    await conn.execute(
                        f"UPDATE {tbl_name} SET object_type = 'history' WHERE object_type = 'memory_store'"
                    )
                    old_constraint = await conn.fetchval(
                        "SELECT conname FROM pg_constraint WHERE conrelid = $1::regclass "
                        "AND contype = 'c' AND pg_get_constraintdef(oid) LIKE '%%memory_store%%'",
                        tbl_name,
                    )
                    if old_constraint:
                        await conn.execute(f"ALTER TABLE {tbl_name} DROP CONSTRAINT {old_constraint}")
                        await conn.execute(
                            f"ALTER TABLE {tbl_name} ADD CHECK(object_type IN ('chat', 'notebook', 'history'))"
                        )

        # Create schema (idempotent — CREATE TABLE IF NOT EXISTS)
        await conn.execute(SCHEMA)
        # Migration: make workspace_id nullable for personal items
        for table in ("notebooks", "histories", "decks"):
            await conn.execute(
                f"ALTER TABLE {table} ALTER COLUMN workspace_id DROP NOT NULL"
            )

        # Migration: add agent-owned resource columns to users
        for col, ref_table in [("notebook_id", "notebooks"), ("history_id", "histories")]:
            has_col = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = $1", col,
            )
            if not has_col:
                await conn.execute(
                    f"ALTER TABLE users ADD COLUMN {col} UUID REFERENCES {ref_table}(id) ON DELETE SET NULL"
                )

        # Migration: add embedding column to history_events (pgvector)
        has_embedding = await conn.fetchval(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'history_events' AND column_name = 'embedding'"
        )
        if not has_embedding:
            await conn.execute(
                "ALTER TABLE history_events ADD COLUMN embedding vector(384)"
            )

        # Migration: add content_hash and metadata to notebook_pages
        for col, col_type, col_default in [
            ("content_hash", "VARCHAR(64)", None),
            ("metadata", "JSONB", "'{}'"),
        ]:
            has_col = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'notebook_pages' AND column_name = $1", col,
            )
            if not has_col:
                default_clause = f" DEFAULT {col_default}" if col_default else ""
                await conn.execute(
                    f"ALTER TABLE notebook_pages ADD COLUMN {col} {col_type}{default_clause}"
                )

        # Create partial indexes (after all migrations so columns exist)
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
