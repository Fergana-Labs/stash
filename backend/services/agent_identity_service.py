from uuid import UUID

from ..auth import generate_api_key, hash_api_key
from ..database import get_pool

MAX_AGENTS_PER_OWNER = 50


async def create_agent(
    owner_id: UUID,
    name: str,
    display_name: str | None,
    description: str,
) -> tuple[dict, str]:
    """Create an agent identity owned by a human user. Returns (agent_row, raw_api_key)."""
    pool = get_pool()

    # Validate owner is human
    owner = await pool.fetchrow("SELECT type FROM users WHERE id = $1", owner_id)
    if not owner or owner["type"] != "human":
        raise ValueError("Only human users can create agent identities")

    # Rate limit
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM users WHERE owner_id = $1", owner_id
    )
    if count >= MAX_AGENTS_PER_OWNER:
        raise ValueError(f"Maximum of {MAX_AGENTS_PER_OWNER} agents per user")

    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    try:
        row = await pool.fetchrow(
            "INSERT INTO users (name, display_name, type, api_key_hash, description, owner_id) "
            "VALUES ($1, $2, 'agent', $3, $4, $5) "
            "RETURNING id, name, display_name, type, description, owner_id, created_at, last_seen",
            name,
            display_name or name,
            key_hash,
            description,
            owner_id,
        )
    except Exception as e:
        if "unique" in str(e).lower() and "name" in str(e).lower():
            raise ValueError(f"Agent name '{name}' is already taken")
        raise
    return dict(row), api_key


async def list_owner_agents(owner_id: UUID) -> list[dict]:
    """List all agents owned by a user."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, display_name, type, description, owner_id, created_at, last_seen "
        "FROM users WHERE owner_id = $1 ORDER BY created_at",
        owner_id,
    )
    return [dict(r) for r in rows]


async def get_agent(agent_id: UUID, owner_id: UUID) -> dict | None:
    """Get a specific agent. Validates ownership."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, type, description, owner_id, created_at, last_seen "
        "FROM users WHERE id = $1 AND owner_id = $2",
        agent_id,
        owner_id,
    )
    return dict(row) if row else None


async def update_agent(
    agent_id: UUID,
    owner_id: UUID,
    display_name: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Update agent details. Owner only."""
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
        return await get_agent(agent_id, owner_id)
    args.extend([agent_id, owner_id])
    row = await pool.fetchrow(
        f"UPDATE users SET {', '.join(sets)} WHERE id = ${idx} AND owner_id = ${idx + 1} "
        "RETURNING id, name, display_name, type, description, owner_id, created_at, last_seen",
        *args,
    )
    return dict(row) if row else None


async def rotate_agent_key(agent_id: UUID, owner_id: UUID) -> tuple[dict, str] | None:
    """Generate a new API key for an agent. Returns (agent_row, new_api_key) or None."""
    pool = get_pool()
    # Verify ownership
    existing = await pool.fetchrow(
        "SELECT id FROM users WHERE id = $1 AND owner_id = $2", agent_id, owner_id
    )
    if not existing:
        return None
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    row = await pool.fetchrow(
        "UPDATE users SET api_key_hash = $1 WHERE id = $2 "
        "RETURNING id, name, display_name, type, description, owner_id, created_at, last_seen",
        key_hash,
        agent_id,
    )
    return dict(row), api_key


async def delete_agent(agent_id: UUID, owner_id: UUID) -> bool:
    """Delete an agent identity. Returns True if deleted."""
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM users WHERE id = $1 AND owner_id = $2", agent_id, owner_id
    )
    return result == "DELETE 1"
