from uuid import UUID

from ..auth import generate_api_key, hash_api_key
from ..database import get_pool


async def register_user(
    name: str, display_name: str | None, user_type: str, description: str
) -> tuple[dict, str]:
    """Register a new user. Returns (user_row, raw_api_key)."""
    pool = get_pool()
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    try:
        row = await pool.fetchrow(
            "INSERT INTO users (name, display_name, type, api_key_hash, description) "
            "VALUES ($1, $2, $3, $4, $5) "
            "RETURNING id, name, display_name, type, description, created_at, last_seen",
            name,
            display_name or name,
            user_type,
            key_hash,
            description,
        )
    except Exception as e:
        if "unique" in str(e).lower() and "name" in str(e).lower():
            raise ValueError(f"Username '{name}' is already taken")
        raise
    return dict(row), api_key


async def get_user_by_id(user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, type, description, created_at, last_seen "
        "FROM users WHERE id = $1",
        user_id,
    )
    return dict(row) if row else None


async def update_user(
    user_id: UUID, display_name: str | None = None, description: str | None = None
) -> dict:
    pool = get_pool()
    sets = []
    args = []
    idx = 1
    if display_name is not None:
        sets.append(f"display_name = ${idx}")
        args.append(display_name)
        idx += 1
    if description is not None:
        sets.append(f"description = ${idx}")
        args.append(description)
        idx += 1
    if not sets:
        row = await pool.fetchrow(
            "SELECT id, name, display_name, type, description, created_at, last_seen "
            "FROM users WHERE id = $1",
            user_id,
        )
        return dict(row)
    args.append(user_id)
    row = await pool.fetchrow(
        f"UPDATE users SET {', '.join(sets)} WHERE id = ${idx} "
        "RETURNING id, name, display_name, type, description, created_at, last_seen",
        *args,
    )
    return dict(row)
