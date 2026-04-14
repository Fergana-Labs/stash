from uuid import UUID

from ..auth import generate_api_key, hash_api_key, hash_password, verify_password
from ..database import get_pool


async def register_user(
    name: str,
    display_name: str | None,
    user_type: str = "human",
    description: str = "",
    password: str | None = None,
) -> tuple[dict, str]:
    """Register a new user. Returns (user_row, raw_api_key)."""
    pool = get_pool()
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    pw_hash = hash_password(password) if password else None
    try:
        row = await pool.fetchrow(
            "INSERT INTO users (name, display_name, type, api_key_hash, password_hash, description) "
            "VALUES ($1, $2, $3, $4, $5, $6) "
            "RETURNING id, name, display_name, type, description, created_at, last_seen",
            name,
            display_name or name,
            user_type,
            key_hash,
            pw_hash,
            description,
        )
    except Exception as e:
        if "unique" in str(e).lower() and "name" in str(e).lower():
            raise ValueError(f"Username '{name}' is already taken")
        raise
    user = dict(row)

    # Auto-provision a default workspace for new humans. Agent/persona users
    # get their workspaces via the persona flow, so skip them here.
    if user_type == "human":
        from . import workspace_service
        await workspace_service.create_workspace(
            name=f"{user['display_name']}'s Workspace",
            description="",
            creator_id=user["id"],
            is_public=False,
        )
    return user, api_key


async def get_user_by_id(user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, type, description, created_at, last_seen "
        "FROM users WHERE id = $1",
        user_id,
    )
    return dict(row) if row else None


async def update_user(
    user_id: UUID,
    display_name: str | None = None,
    description: str | None = None,
    password: str | None = None,
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
    if password is not None:
        sets.append(f"password_hash = ${idx}")
        args.append(hash_password(password))
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


async def authenticate_by_password(name: str, password: str) -> tuple[dict, str]:
    """Authenticate by username + password. Returns (user_dict, new_api_key)."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, type, description, created_at, last_seen, password_hash "
        "FROM users WHERE name = $1",
        name,
    )
    if not row or not row["password_hash"]:
        raise ValueError("Invalid username or password")
    if not verify_password(password, row["password_hash"]):
        raise ValueError("Invalid username or password")
    # Generate new API key on login
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    await pool.execute(
        "UPDATE users SET api_key_hash = $1, last_seen = now() WHERE id = $2",
        key_hash,
        row["id"],
    )
    user = {k: v for k, v in dict(row).items() if k != "password_hash"}
    return user, api_key
