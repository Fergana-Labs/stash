"""Initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-04-14
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(128),
    type VARCHAR(8) NOT NULL CHECK(type IN ('human', 'persona')),
    api_key_hash VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(72),
    auth0_sub VARCHAR(128) UNIQUE,
    description TEXT DEFAULT '',
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    notebook_id UUID,
    history_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    description TEXT DEFAULT '',
    creator_id UUID NOT NULL REFERENCES users(id),
    invite_code VARCHAR(12) NOT NULL UNIQUE,
    is_public BOOLEAN NOT NULL DEFAULT false,
    ragflow_dataset_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(8) NOT NULL DEFAULT 'member'
        CHECK(role IN ('owner', 'admin', 'member')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,
    description TEXT DEFAULT '',
    creator_id UUID NOT NULL REFERENCES users(id),
    is_dm BOOLEAN NOT NULL DEFAULT false,
    dm_user_a UUID REFERENCES users(id),
    dm_user_b UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_dm_users CHECK (
        NOT is_dm OR (dm_user_a IS NOT NULL AND dm_user_b IS NOT NULL AND dm_user_a < dm_user_b)
    )
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    message_type VARCHAR(8) DEFAULT 'text' CHECK(message_type IN ('text', 'system')),
    reply_to_id UUID REFERENCES chat_messages(id),
    attachments JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS chat_watches (
    persona_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    last_read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (persona_id, chat_id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS notebooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS notebook_folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notebook_id UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(notebook_id, name)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS notebook_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notebook_id UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    folder_id UUID REFERENCES notebook_folders(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    content_markdown TEXT NOT NULL DEFAULT '',
    content_hash VARCHAR(64),
    metadata JSONB DEFAULT '{}',
    embedding vector(384),
    created_by UUID NOT NULL REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS page_links (
    source_page_id UUID NOT NULL REFERENCES notebook_pages(id) ON DELETE CASCADE,
    target_page_id UUID NOT NULL REFERENCES notebook_pages(id) ON DELETE CASCADE,
    link_text VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_page_id, target_page_id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS history_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by UUID REFERENCES users(id),
    agent_name VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    session_id VARCHAR(64),
    tool_name VARCHAR(128),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    attachments JSONB,
    embedding vector(384),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS injection_configs (
    persona_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    budget_tokens INTEGER NOT NULL DEFAULT 4000,
    min_score REAL NOT NULL DEFAULT 0.01,
    recency_intervals REAL[] NOT NULL DEFAULT '{1.0,4.0,24.0,72.0,168.0,720.0}',
    staleness_decay_fast REAL NOT NULL DEFAULT 0.15,
    staleness_decay_slow REAL NOT NULL DEFAULT 0.40,
    staleness_fast_threshold_seconds REAL NOT NULL DEFAULT 60.0,
    embedding_dims INTEGER NOT NULL DEFAULT 384,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS injection_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(64) NOT NULL,
    injected_items JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    scored_at TIMESTAMPTZ,
    UNIQUE(persona_id, session_id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS sleep_configs (
    persona_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT true,
    interval_minutes INTEGER NOT NULL DEFAULT 60,
    max_pattern_cards INTEGER NOT NULL DEFAULT 500,
    monologue_batch_size INTEGER NOT NULL DEFAULT 20,
    monologue_model VARCHAR(64) NOT NULL DEFAULT 'claude-haiku-4-5-20251001',
    curation_model VARCHAR(64) NOT NULL DEFAULT 'claude-haiku-4-5-20251001',
    curation_sources JSONB NOT NULL DEFAULT '["history"]',
    curation_rules JSONB NOT NULL DEFAULT '{}',
    workspace_ids UUID[] DEFAULT '{}',
    agent_name_filter TEXT[] DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS decks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '',
    html_content TEXT NOT NULL DEFAULT '',
    deck_type VARCHAR(32) DEFAULT 'freeform'
        CHECK(deck_type IN ('freeform', 'slides', 'dashboard')),
    created_by UUID NOT NULL REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS deck_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    token VARCHAR(16) NOT NULL UNIQUE,
    name VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT true,
    require_email BOOLEAN NOT NULL DEFAULT false,
    passcode_hash VARCHAR(72),
    allow_download BOOLEAN NOT NULL DEFAULT true,
    expires_at TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS deck_share_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    share_id UUID NOT NULL REFERENCES deck_shares(id) ON DELETE CASCADE,
    session_token VARCHAR(96) NOT NULL UNIQUE,
    viewer_email VARCHAR(255),
    viewer_ip VARCHAR(45),
    user_agent TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_duration_seconds INTEGER NOT NULL DEFAULT 0
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS deck_share_page_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    view_id UUID NOT NULL REFERENCES deck_share_views(id) ON DELETE CASCADE,
    page_identifier VARCHAR(255) NOT NULL,
    entered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    UNIQUE(view_id, page_identifier)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS tables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '',
    columns JSONB NOT NULL DEFAULT '[]',
    views JSONB NOT NULL DEFAULT '[]',
    embedding_config JSONB,
    created_by UUID NOT NULL REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS table_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
    data JSONB NOT NULL DEFAULT '{}',
    row_order INTEGER NOT NULL DEFAULT 0,
    embedding vector(384),
    created_by UUID NOT NULL REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS object_permissions (
    object_type VARCHAR(16) NOT NULL CHECK(object_type IN ('chat', 'notebook', 'history', 'deck', 'table')),
    object_id UUID NOT NULL,
    visibility VARCHAR(16) NOT NULL DEFAULT 'inherit'
        CHECK(visibility IN ('inherit', 'private', 'public')),
    PRIMARY KEY (object_type, object_id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS object_shares (
    object_type VARCHAR(16) NOT NULL CHECK(object_type IN ('chat', 'notebook', 'history', 'deck', 'table')),
    object_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission VARCHAR(8) NOT NULL DEFAULT 'read'
        CHECK(permission IN ('read', 'write', 'admin')),
    granted_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (object_type, object_id, user_id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128) NOT NULL,
    size_bytes BIGINT NOT NULL,
    storage_key VARCHAR(512) NOT NULL,
    uploaded_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    file_id UUID REFERENCES files(id),
    name VARCHAR(255) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    ragflow_dataset_id VARCHAR(255),
    ragflow_doc_id VARCHAR(255),
    status VARCHAR(32) DEFAULT 'pending'
        CHECK(status IN ('pending', 'processing', 'ready', 'error')),
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    secret_hash VARCHAR(64),
    event_filter TEXT[] DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, user_id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id UUID NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'delivered', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS embedding_projections (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type VARCHAR(32) NOT NULL DEFAULT '_all',
    points JSONB NOT NULL DEFAULT '[]',
    embedding_count INTEGER NOT NULL DEFAULT 0,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, source_type)
)
""")

    # Standard indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_api_key_hash ON users(api_key_hash)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_owner ON users(owner_id) WHERE owner_id IS NOT NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_invite_code ON workspaces(invite_code)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chats_workspace ON chats(workspace_id) WHERE workspace_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_created ON chat_messages(chat_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_fts ON chat_messages USING GIN(to_tsvector('english', content))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_watches_persona ON chat_watches(persona_id) WHERE enabled = true"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_notebooks_workspace ON notebooks(workspace_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notebook_pages_notebook ON notebook_pages(notebook_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_notebook_pages_folder ON notebook_pages(folder_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notebook_folders_notebook ON notebook_folders(notebook_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_events_workspace ON history_events(workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_events_agent_session ON history_events(agent_name, session_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_events_fts ON history_events USING GIN(to_tsvector('english', content))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_events_metadata ON history_events USING GIN(metadata)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notebook_pages_fts ON notebook_pages USING GIN(to_tsvector('english', content_markdown))"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_page_links_target ON page_links(target_page_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_injection_sessions_persona ON injection_sessions(persona_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_decks_workspace ON decks(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_deck_shares_deck ON deck_shares(deck_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_deck_shares_token ON deck_shares(token)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deck_share_views_share ON deck_share_views(share_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deck_share_views_session ON deck_share_views(session_token)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deck_share_page_views_view ON deck_share_page_views(view_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_tables_workspace ON tables(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_table_rows_table ON table_rows(table_id, row_order)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_table_rows_data ON table_rows USING GIN(data)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_files_workspace ON files(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(workspace_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_object_shares_user ON object_shares(user_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_webhooks_workspace ON webhooks(workspace_id) WHERE is_active = true"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_pending ON webhook_deliveries(status, next_retry_at) WHERE status = 'pending'"
    )

    # Partial / HNSW indexes
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_dm_unique_pair ON chats(dm_user_a, dm_user_b) WHERE is_dm = true"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_notebook_pages_root_unique ON notebook_pages(notebook_id, name) WHERE folder_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_notebook_pages_folder_unique ON notebook_pages(notebook_id, folder_id, name) WHERE folder_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_notebook_unique ON notebooks(created_by, name) WHERE workspace_id IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notebooks_personal ON notebooks(created_by) WHERE workspace_id IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chats_personal ON chats(creator_id) WHERE workspace_id IS NULL AND is_dm = false"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_deck_unique ON decks(created_by, name) WHERE workspace_id IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_decks_personal ON decks(created_by) WHERE workspace_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_table_unique ON tables(created_by, name) WHERE workspace_id IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tables_personal ON tables(created_by) WHERE workspace_id IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_personal ON files(uploaded_by) WHERE workspace_id IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_injection_sessions_pending ON injection_sessions(persona_id) WHERE completed_at IS NOT NULL AND scored_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_table_rows_embedding ON table_rows USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notebook_pages_embedding ON notebook_pages USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_events_embedding ON history_events USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    # Drop in reverse FK-dependency order
    op.execute("DROP TABLE IF EXISTS embedding_projections CASCADE")
    op.execute("DROP TABLE IF EXISTS webhook_deliveries CASCADE")
    op.execute("DROP TABLE IF EXISTS webhooks CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS files CASCADE")
    op.execute("DROP TABLE IF EXISTS object_shares CASCADE")
    op.execute("DROP TABLE IF EXISTS object_permissions CASCADE")
    op.execute("DROP TABLE IF EXISTS table_rows CASCADE")
    op.execute("DROP TABLE IF EXISTS tables CASCADE")
    op.execute("DROP TABLE IF EXISTS deck_share_page_views CASCADE")
    op.execute("DROP TABLE IF EXISTS deck_share_views CASCADE")
    op.execute("DROP TABLE IF EXISTS deck_shares CASCADE")
    op.execute("DROP TABLE IF EXISTS decks CASCADE")
    op.execute("DROP TABLE IF EXISTS sleep_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS injection_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS injection_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS history_events CASCADE")
    op.execute("DROP TABLE IF EXISTS page_links CASCADE")
    op.execute("DROP TABLE IF EXISTS notebook_pages CASCADE")
    op.execute("DROP TABLE IF EXISTS notebook_folders CASCADE")
    op.execute("DROP TABLE IF EXISTS notebooks CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_watches CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS chats CASCADE")
    op.execute("DROP TABLE IF EXISTS workspace_members CASCADE")
    op.execute("DROP TABLE IF EXISTS workspaces CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
