"""DM service: direct messages between two users (workspace-less chats)."""

from uuid import UUID

from ..database import get_pool


async def get_or_create_dm(user_id: UUID, target_user_id: UUID) -> dict:
    """Get or create a DM chat between two users."""
    if user_id == target_user_id:
        raise ValueError("Cannot start a DM with yourself")

    pool = get_pool()

    # Sort user IDs for consistent storage (dm_user_a < dm_user_b)
    user_a = min(user_id, target_user_id)
    user_b = max(user_id, target_user_id)

    # Look for existing DM
    row = await pool.fetchrow(
        "SELECT id, workspace_id, name, description, creator_id, is_dm, created_at, updated_at "
        "FROM chats WHERE is_dm = true AND dm_user_a = $1 AND dm_user_b = $2",
        user_a, user_b,
    )

    if row:
        chat = dict(row)
    else:
        # Create new DM
        chat_row = await pool.fetchrow(
            "INSERT INTO chats (name, description, creator_id, is_dm, dm_user_a, dm_user_b) "
            "VALUES ('DM', '', $1, true, $2, $3) "
            "RETURNING id, workspace_id, name, description, creator_id, is_dm, created_at, updated_at",
            user_id, user_a, user_b,
        )
        chat = dict(chat_row)

    # Fetch the other user's info
    other_user = await pool.fetchrow(
        "SELECT id, name, display_name, type FROM users WHERE id = $1",
        target_user_id,
    )

    chat["other_user"] = dict(other_user) if other_user else None

    # Get last message timestamp
    last_msg = await pool.fetchval(
        "SELECT MAX(created_at) FROM chat_messages WHERE chat_id = $1",
        chat["id"],
    )
    chat["last_message_at"] = last_msg.isoformat() if last_msg else None

    return chat


async def list_dms(user_id: UUID) -> list[dict]:
    """List all DM conversations for a user, sorted by most recent message."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT c.id, c.workspace_id, c.name, c.description, c.creator_id,
               c.is_dm, c.dm_user_a, c.dm_user_b, c.created_at, c.updated_at,
               (SELECT MAX(m.created_at) FROM chat_messages m WHERE m.chat_id = c.id) AS last_message_at
        FROM chats c
        WHERE c.is_dm = true AND (c.dm_user_a = $1 OR c.dm_user_b = $1)
        ORDER BY last_message_at DESC NULLS LAST, c.created_at DESC
        """,
        user_id,
    )

    dms = []
    for row in rows:
        dm = dict(row)
        dm["last_message_at"] = (
            dm["last_message_at"].isoformat() if dm["last_message_at"] else None
        )

        # Get the other user
        other_id = dm["dm_user_b"] if dm["dm_user_a"] == user_id else dm["dm_user_a"]
        other = await pool.fetchrow(
            "SELECT id, name, display_name, type FROM users WHERE id = $1",
            other_id,
        )
        dm["other_user"] = dict(other) if other else None
        dms.append(dm)

    return dms


async def is_dm_participant(chat_id: UUID, user_id: UUID) -> bool:
    """Check if a user is a participant in a DM."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM chats WHERE id = $1 AND is_dm = true AND (dm_user_a = $2 OR dm_user_b = $2)",
        chat_id, user_id,
    )
    return row is not None


async def find_users(query: str, current_user_id: UUID, limit: int = 20) -> list[dict]:
    """Search users by name or display_name."""
    pool = get_pool()
    pattern = f"%{query}%"
    rows = await pool.fetch(
        "SELECT id, name, display_name, type FROM users "
        "WHERE id != $1 AND (name ILIKE $2 OR display_name ILIKE $2) "
        "ORDER BY name LIMIT $3",
        current_user_id, pattern, limit,
    )
    return [dict(r) for r in rows]
