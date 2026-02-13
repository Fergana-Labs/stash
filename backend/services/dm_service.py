from uuid import UUID

from ..database import get_pool


async def get_or_create_dm(user_id: UUID, target_user_id: UUID) -> dict:
    """Get or create a DM room between two users. Returns room dict with other_user info."""
    if user_id == target_user_id:
        raise ValueError("Cannot start a DM with yourself")

    pool = get_pool()

    # Look for an existing DM room where both users are members
    row = await pool.fetchrow(
        """
        SELECT r.id, r.name, r.description, r.creator_id, r.invite_code,
               r.is_public, r.type, r.created_at
        FROM rooms r
        WHERE r.type = 'dm'
          AND EXISTS (SELECT 1 FROM room_members rm WHERE rm.room_id = r.id AND rm.user_id = $1)
          AND EXISTS (SELECT 1 FROM room_members rm WHERE rm.room_id = r.id AND rm.user_id = $2)
        LIMIT 1
        """,
        user_id,
        target_user_id,
    )

    if row:
        room = dict(row)
    else:
        # Create a new DM room
        import secrets

        invite_code = secrets.token_urlsafe(6)[:8]
        room_row = await pool.fetchrow(
            "INSERT INTO rooms (name, description, creator_id, invite_code, is_public, type) "
            "VALUES ('DM', '', $1, $2, false, 'dm') "
            "RETURNING id, name, description, creator_id, invite_code, is_public, type, created_at",
            user_id,
            invite_code,
        )
        room = dict(room_row)
        # Add both users as members
        await pool.execute(
            "INSERT INTO room_members (room_id, user_id, role) VALUES ($1, $2, 'owner')",
            room["id"],
            user_id,
        )
        await pool.execute(
            "INSERT INTO room_members (room_id, user_id, role) VALUES ($1, $2, 'member')",
            room["id"],
            target_user_id,
        )

    # Fetch the other user's info
    other_user = await pool.fetchrow(
        "SELECT id, name, display_name, type FROM users WHERE id = $1",
        target_user_id,
    )

    room["member_count"] = 2
    room["other_user"] = dict(other_user) if other_user else None

    # Get last message timestamp
    last_msg = await pool.fetchval(
        "SELECT MAX(created_at) FROM messages WHERE room_id = $1",
        room["id"],
    )
    room["last_message_at"] = last_msg.isoformat() if last_msg else None

    return room


async def list_dms(user_id: UUID) -> list[dict]:
    """List all DM conversations for a user, sorted by most recent message."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT r.id, r.name, r.description, r.creator_id, r.invite_code,
               r.is_public, r.type, r.created_at,
               (SELECT MAX(m.created_at) FROM messages m WHERE m.room_id = r.id) AS last_message_at
        FROM rooms r
        INNER JOIN room_members rm ON r.id = rm.room_id
        WHERE rm.user_id = $1 AND r.type = 'dm'
        ORDER BY last_message_at DESC NULLS LAST, r.created_at DESC
        """,
        user_id,
    )

    dms = []
    for row in rows:
        dm = dict(row)
        dm["last_message_at"] = (
            dm["last_message_at"].isoformat() if dm["last_message_at"] else None
        )
        dm["member_count"] = 2

        # Get the other user in this DM
        other = await pool.fetchrow(
            """
            SELECT u.id, u.name, u.display_name, u.type
            FROM room_members rm
            INNER JOIN users u ON rm.user_id = u.id
            WHERE rm.room_id = $1 AND rm.user_id != $2
            LIMIT 1
            """,
            dm["id"],
            user_id,
        )
        dm["other_user"] = dict(other) if other else None
        dms.append(dm)

    return dms


async def find_users(query: str, current_user_id: UUID, limit: int = 20) -> list[dict]:
    """Search users by name or display_name (case-insensitive). Excludes current user."""
    pool = get_pool()
    pattern = f"%{query}%"
    rows = await pool.fetch(
        """
        SELECT id, name, display_name, type
        FROM users
        WHERE id != $1
          AND (name ILIKE $2 OR display_name ILIKE $2)
        ORDER BY name
        LIMIT $3
        """,
        current_user_id,
        pattern,
        limit,
    )
    return [dict(r) for r in rows]
