"""Drop unused chats and chat_messages tables.

The chat/rooms/DMs product surface was never built on the backend
(no router). The tables have no readers or writers in live code.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chat_messages_fts")
    op.execute("DROP INDEX IF EXISTS idx_chat_messages_chat_created")
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")

    op.execute("DROP INDEX IF EXISTS idx_dm_unique_pair")
    op.execute("DROP INDEX IF EXISTS idx_chats_personal")
    op.execute("DROP INDEX IF EXISTS idx_chats_workspace")
    op.execute("DROP TABLE IF EXISTS chats CASCADE")


def downgrade() -> None:
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
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chats_workspace "
        "ON chats(workspace_id) WHERE workspace_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_created "
        "ON chat_messages(chat_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_fts "
        "ON chat_messages USING GIN(to_tsvector('english', content))"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_dm_unique_pair "
        "ON chats(dm_user_a, dm_user_b) WHERE is_dm = true"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chats_personal "
        "ON chats(creator_id) WHERE workspace_id IS NULL AND is_dm = false"
    )
