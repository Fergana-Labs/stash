"""Chat service: messaging, search, CRUD for chats within workspaces."""

from datetime import datetime
from uuid import UUID

from ..database import get_pool


async def create_chat(
    workspace_id: UUID, name: str, description: str, creator_id: UUID,
) -> dict:
    """Create a chat within a workspace."""
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO chats (workspace_id, name, description, creator_id) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, workspace_id, name, description, creator_id, is_dm, created_at, updated_at",
        workspace_id, name, description, creator_id,
    )
    return dict(row)


async def get_chat(chat_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, name, description, creator_id, is_dm, created_at, updated_at "
        "FROM chats WHERE id = $1",
        chat_id,
    )
    return dict(row) if row else None


async def list_chats(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, name, description, creator_id, is_dm, created_at, updated_at "
        "FROM chats WHERE workspace_id = $1 AND is_dm = false ORDER BY created_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def delete_chat(chat_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM chats WHERE id = $1 AND workspace_id = $2",
        chat_id, workspace_id,
    )
    return result == "DELETE 1"


# --- Messages ---


async def send_message(
    chat_id: UUID, sender_id: UUID, content: str,
    message_type: str = "text", reply_to_id: UUID | None = None,
) -> dict:
    """Send a message to a chat. Returns message with sender info."""
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO chat_messages (chat_id, sender_id, content, message_type, reply_to_id) "
        "VALUES ($1, $2, $3, $4, $5) "
        "RETURNING id, chat_id, sender_id, content, message_type, reply_to_id, created_at",
        chat_id, sender_id, content, message_type, reply_to_id,
    )
    msg = dict(row)
    # Fetch sender info
    sender = await pool.fetchrow(
        "SELECT name, display_name, type FROM users WHERE id = $1", sender_id,
    )
    if sender:
        msg["sender_name"] = sender["name"]
        msg["sender_display_name"] = sender["display_name"]
        msg["sender_type"] = sender["type"]
    return msg


async def get_messages(
    chat_id: UUID,
    limit: int = 50,
    after: str | None = None,
    before: str | None = None,
) -> tuple[list[dict], bool]:
    """Get messages for a chat. Returns (messages, has_more)."""
    pool = get_pool()
    limit = min(limit, 100)

    conditions = ["m.chat_id = $1"]
    args: list = [chat_id]
    idx = 2

    if after:
        conditions.append(f"m.created_at > ${idx}")
        args.append(after)
        idx += 1
    if before:
        conditions.append(f"m.created_at < ${idx}")
        args.append(before)
        idx += 1

    where = " AND ".join(conditions)
    args.append(limit + 1)

    rows = await pool.fetch(
        f"SELECT m.id, m.chat_id, m.sender_id, m.content, m.message_type, "
        f"m.reply_to_id, m.created_at, "
        f"u.name AS sender_name, u.display_name AS sender_display_name, u.type AS sender_type "
        f"FROM chat_messages m JOIN users u ON u.id = m.sender_id "
        f"WHERE {where} ORDER BY m.created_at ASC LIMIT ${idx}",
        *args,
    )

    messages = [dict(r) for r in rows]
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]
    return messages, has_more


async def search_messages(
    chat_id: UUID, query: str, limit: int = 20,
) -> list[dict]:
    """Full-text search on chat messages."""
    pool = get_pool()
    limit = min(limit, 100)
    rows = await pool.fetch(
        "SELECT m.id, m.chat_id, m.sender_id, m.content, m.message_type, "
        "m.reply_to_id, m.created_at, "
        "u.name AS sender_name, u.display_name AS sender_display_name, u.type AS sender_type, "
        "ts_rank(to_tsvector('english', m.content), websearch_to_tsquery('english', $2)) AS rank "
        "FROM chat_messages m JOIN users u ON u.id = m.sender_id "
        "WHERE m.chat_id = $1 AND to_tsvector('english', m.content) @@ websearch_to_tsquery('english', $2) "
        "ORDER BY rank DESC LIMIT $3",
        chat_id, query, limit,
    )
    return [dict(r) for r in rows]
