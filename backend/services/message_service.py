from datetime import datetime
from uuid import UUID

from ..database import get_pool


async def send_message(
    room_id: UUID,
    sender_id: UUID,
    content: str,
    message_type: str = "text",
    reply_to_id: UUID | None = None,
    matrix_event_id: str | None = None,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO messages (room_id, sender_id, content, message_type, reply_to_id, matrix_event_id) "
        "VALUES ($1, $2, $3, $4, $5, $6) "
        "RETURNING id, room_id, sender_id, content, message_type, reply_to_id, matrix_event_id, created_at",
        room_id,
        sender_id,
        content,
        message_type,
        reply_to_id,
        matrix_event_id,
    )
    msg = dict(row)
    # Fetch sender info
    sender = await pool.fetchrow(
        "SELECT name, display_name, type FROM users WHERE id = $1", sender_id
    )
    msg["sender_name"] = sender["name"]
    msg["sender_display_name"] = sender["display_name"]
    msg["sender_type"] = sender["type"]
    return msg


async def get_messages(
    room_id: UUID,
    after: datetime | None = None,
    before: datetime | None = None,
    limit: int = 50,
) -> tuple[list[dict], bool]:
    pool = get_pool()
    limit = min(limit, 100)
    query = (
        "SELECT m.id, m.room_id, m.sender_id, m.content, m.message_type, "
        "m.reply_to_id, m.matrix_event_id, m.created_at, "
        "u.name AS sender_name, u.display_name AS sender_display_name, u.type AS sender_type "
        "FROM messages m INNER JOIN users u ON m.sender_id = u.id "
        "WHERE m.room_id = $1"
    )
    args: list = [room_id]
    idx = 2

    if after:
        query += f" AND m.created_at > ${idx}"
        args.append(after)
        idx += 1
    if before:
        query += f" AND m.created_at < ${idx}"
        args.append(before)
        idx += 1

    # Fetch one extra to check has_more
    query += f" ORDER BY m.created_at DESC LIMIT ${idx}"
    args.append(limit + 1)

    rows = await pool.fetch(query, *args)
    has_more = len(rows) > limit
    messages = [dict(r) for r in rows[:limit]]
    messages.reverse()  # Chronological order
    return messages, has_more


async def set_matrix_event_id(message_id: UUID, matrix_event_id: str):
    pool = get_pool()
    await pool.execute(
        "UPDATE messages SET matrix_event_id = $1 WHERE id = $2",
        matrix_event_id,
        message_id,
    )


async def message_exists_by_matrix_event(matrix_event_id: str) -> bool:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM messages WHERE matrix_event_id = $1", matrix_event_id
    )
    return row is not None
