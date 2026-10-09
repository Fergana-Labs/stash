"""Stable origin identifiers and owner-scoped display names for agent traces."""

from uuid import UUID

from ...database import get_pool


def source_id(metadata: dict, source_format: str) -> str:
    for key in ("source_id", "agent", "source"):
        value = metadata.get(key)
        if isinstance(value, str) and 0 < len(value.strip()) <= 200:
            return value.strip()
    return source_format


def default_name(identifier: str, owner_name: str = "") -> str:
    coding_agents = {"codex": "Codex", "claude_code": "Claude Code"}
    if identifier in coding_agents:
        agent = coding_agents[identifier]
        return f"{owner_name}’s {agent}" if owner_name else agent
    return {
        "otel": "OpenTelemetry",
        "stash": "Stash",
        "langsmith": "LangSmith",
        "langfuse": "Langfuse",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
    }.get(identifier, identifier)


async def names(rows) -> dict[tuple[UUID, str], str]:
    if not rows:
        return {}
    saved = await get_pool().fetch(
        "SELECT owner_user_id, source_id, name FROM rm_trace_sources WHERE owner_user_id=ANY($1::uuid[]) AND source_id=ANY($2::text[])",
        list({r["owner_user_id"] for r in rows}),
        list({source_id(r["metadata"] or {}, r["source_format"]) for r in rows}),
    )
    return {(r["owner_user_id"], r["source_id"]): r["name"] for r in saved}


async def rename(owner: UUID, identifier: str, name: str) -> dict:
    await get_pool().execute(
        """INSERT INTO rm_trace_sources (owner_user_id, source_id, name) VALUES ($1,$2,$3)
        ON CONFLICT (owner_user_id,source_id) DO UPDATE SET name=EXCLUDED.name""",
        owner,
        identifier,
        name,
    )
    return {"source_id": identifier, "source_name": name}
