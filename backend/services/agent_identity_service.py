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
    """Create an agent identity owned by a human user. Returns (agent_row, raw_api_key).

    Auto-provisions a personal notebook and history store for the agent.
    """
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

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Create the agent user
            try:
                row = await conn.fetchrow(
                    "INSERT INTO users (name, display_name, type, api_key_hash, description, owner_id) "
                    "VALUES ($1, $2, 'agent', $3, $4, $5) "
                    "RETURNING id, name, display_name, type, description, owner_id, notebook_id, history_id, created_at, last_seen",
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

            agent_id = row["id"]

            # Auto-provision personal notebook
            nb_row = await conn.fetchrow(
                "INSERT INTO notebooks (workspace_id, name, description, created_by) "
                "VALUES (NULL, $1, $2, $3) RETURNING id",
                name, f"Notebook for agent {name}", agent_id,
            )

            # Auto-provision personal history store
            hist_row = await conn.fetchrow(
                "INSERT INTO histories (workspace_id, name, description, created_by) "
                "VALUES (NULL, $1, $2, $3) RETURNING id",
                name, f"History for agent {name}", agent_id,
            )

            # Link resources to agent
            await conn.execute(
                "UPDATE users SET notebook_id = $1, history_id = $2 WHERE id = $3",
                nb_row["id"], hist_row["id"], agent_id,
            )

    agent = dict(row)
    agent["notebook_id"] = nb_row["id"]
    agent["history_id"] = hist_row["id"]
    return agent, api_key


async def list_owner_agents(owner_id: UUID) -> list[dict]:
    """List all agents owned by a user."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, display_name, type, description, owner_id, "
        "notebook_id, history_id, created_at, last_seen "
        "FROM users WHERE owner_id = $1 ORDER BY created_at",
        owner_id,
    )
    return [dict(r) for r in rows]


async def get_agent(agent_id: UUID, owner_id: UUID) -> dict | None:
    """Get a specific agent. Validates ownership."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, type, description, owner_id, "
        "notebook_id, history_id, created_at, last_seen "
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
        "RETURNING id, name, display_name, type, description, owner_id, notebook_id, history_id, created_at, last_seen",
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
        "RETURNING id, name, display_name, type, description, owner_id, notebook_id, history_id, created_at, last_seen",
        key_hash,
        agent_id,
    )
    return dict(row), api_key


async def delete_agent(agent_id: UUID, owner_id: UUID) -> bool:
    """Delete an agent identity and its provisioned resources. Returns True if deleted."""
    pool = get_pool()

    # Fetch resource IDs before deleting
    agent = await pool.fetchrow(
        "SELECT notebook_id, history_id FROM users WHERE id = $1 AND owner_id = $2",
        agent_id, owner_id,
    )
    if not agent:
        return False

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Delete agent user (cascades to workspace_members etc.)
            result = await conn.execute(
                "DELETE FROM users WHERE id = $1 AND owner_id = $2", agent_id, owner_id,
            )
            if result != "DELETE 1":
                return False
            # Clean up provisioned resources
            if agent["notebook_id"]:
                await conn.execute("DELETE FROM notebooks WHERE id = $1", agent["notebook_id"])
            if agent["history_id"]:
                await conn.execute("DELETE FROM histories WHERE id = $1", agent["history_id"])

    return True


async def get_agent_resources(agent_id: UUID) -> dict | None:
    """Get the notebook_id and history_id for an agent."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT notebook_id, history_id FROM users WHERE id = $1 AND type = 'agent'",
        agent_id,
    )
    return dict(row) if row else None


async def provision_existing_agent(agent_id: UUID) -> dict | None:
    """Provision notebook + history for an existing agent that doesn't have them yet."""
    pool = get_pool()

    agent = await pool.fetchrow(
        "SELECT id, name, notebook_id, history_id FROM users WHERE id = $1 AND type = 'agent'",
        agent_id,
    )
    if not agent:
        return None

    async with pool.acquire() as conn:
        async with conn.transaction():
            notebook_id = agent["notebook_id"]
            history_id = agent["history_id"]

            if not notebook_id:
                nb_row = await conn.fetchrow(
                    "INSERT INTO notebooks (workspace_id, name, description, created_by) "
                    "VALUES (NULL, $1, $2, $3) RETURNING id",
                    agent["name"], f"Notebook for agent {agent['name']}", agent_id,
                )
                notebook_id = nb_row["id"]

            if not history_id:
                hist_row = await conn.fetchrow(
                    "INSERT INTO histories (workspace_id, name, description, created_by) "
                    "VALUES (NULL, $1, $2, $3) RETURNING id",
                    agent["name"], f"History for agent {agent['name']}", agent_id,
                )
                history_id = hist_row["id"]

            await conn.execute(
                "UPDATE users SET notebook_id = $1, history_id = $2 WHERE id = $3",
                notebook_id, history_id, agent_id,
            )

    return {"notebook_id": notebook_id, "history_id": history_id}
