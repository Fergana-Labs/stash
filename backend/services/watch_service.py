"""Watch service: per-persona chat notification subscriptions with unread tracking."""

from uuid import UUID

from ..database import get_pool


async def watch_chat(persona_id: UUID, chat_id: UUID, workspace_id: UUID | None = None) -> dict:
    """Subscribe a persona to a chat. Resolves workspace_id from the chat if not provided."""
    pool = get_pool()

    chat = await pool.fetchrow("SELECT id, workspace_id FROM chats WHERE id = $1", chat_id)
    if not chat:
        raise ValueError(f"Chat {chat_id} not found")
    ws_id = workspace_id or chat["workspace_id"]

    if ws_id:
        from . import workspace_service
        if not await workspace_service.is_member(ws_id, persona_id):
            raise ValueError(f"Persona is not a member of workspace for chat {chat_id}")

    row = await pool.fetchrow(
        "INSERT INTO chat_watches (persona_id, chat_id, workspace_id, last_read_at) "
        "VALUES ($1, $2, $3, now()) "
        "ON CONFLICT (persona_id, chat_id) DO UPDATE SET enabled = true, workspace_id = $3 "
        "RETURNING persona_id, chat_id, workspace_id, last_read_at, enabled, created_at",
        persona_id, chat_id, ws_id,
    )
    return dict(row)


async def unwatch_chat(persona_id: UUID, chat_id: UUID) -> bool:
    """Disable a chat watch. Returns True if a row was updated."""
    pool = get_pool()
    result = await pool.execute(
        "UPDATE chat_watches SET enabled = false "
        "WHERE persona_id = $1 AND chat_id = $2 AND enabled = true",
        persona_id, chat_id,
    )
    return result.endswith("1")


async def list_watches(persona_id: UUID) -> list[dict]:
    """List all active watches for a persona."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT cw.persona_id, cw.chat_id, cw.workspace_id, cw.last_read_at, "
        "cw.enabled, cw.created_at, "
        "c.name AS chat_name, COALESCE(w.name, '') AS workspace_name "
        "FROM chat_watches cw "
        "JOIN chats c ON c.id = cw.chat_id "
        "LEFT JOIN workspaces w ON w.id = cw.workspace_id "
        "WHERE cw.persona_id = $1 AND cw.enabled = true "
        "ORDER BY cw.created_at",
        persona_id,
    )
    return [dict(r) for r in rows]


async def get_unread(persona_id: UUID) -> list[dict]:
    """Get unread message counts for all watched chats."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT cw.chat_id, c.name AS chat_name, cw.workspace_id, "
        "COALESCE(w.name, '') AS workspace_name, cw.last_read_at, "
        "COUNT(m.id)::int AS unread_count, "
        "MAX(m.created_at) AS latest_message_at "
        "FROM chat_watches cw "
        "JOIN chats c ON c.id = cw.chat_id "
        "LEFT JOIN workspaces w ON w.id = cw.workspace_id "
        "LEFT JOIN chat_messages m ON m.chat_id = cw.chat_id "
        "    AND m.created_at > cw.last_read_at "
        "    AND m.sender_id != $1 "
        "WHERE cw.persona_id = $1 AND cw.enabled = true "
        "GROUP BY cw.chat_id, c.name, cw.workspace_id, w.name, cw.last_read_at",
        persona_id,
    )
    return [dict(r) for r in rows]


async def mark_read(persona_id: UUID, chat_id: UUID) -> bool:
    """Mark a watched chat as read (advance last_read_at to now)."""
    pool = get_pool()
    result = await pool.execute(
        "UPDATE chat_watches SET last_read_at = now() "
        "WHERE persona_id = $1 AND chat_id = $2 AND enabled = true",
        persona_id, chat_id,
    )
    return result.endswith("1")


async def auto_mark_read(sender_id: UUID, chat_id: UUID) -> None:
    """Auto-advance last_read_at when a watched persona sends a message."""
    pool = get_pool()
    await pool.execute(
        "UPDATE chat_watches SET last_read_at = now() "
        "WHERE persona_id = $1 AND chat_id = $2 AND enabled = true",
        sender_id, chat_id,
    )
