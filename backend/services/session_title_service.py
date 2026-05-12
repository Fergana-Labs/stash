"""AI-generated labels for agent sessions."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from ..config import settings
from ..database import get_pool

MAX_BATCH_SIZE = 10
MAX_SOURCE_CHARS = 1_400


def _source_hash(session: dict) -> str:
    summary = session.get("stash_summary") or ""
    last_at = session.get("last_at")
    if hasattr(last_at, "isoformat"):
        last_at = last_at.isoformat()
    raw = f"{session['session_id']}|{session.get('event_count')}|{last_at}|{summary}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _clean_text(text: str) -> str:
    return " ".join(text.split())


def _json_text(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if len(lines) < 3 or not lines[-1].startswith("```"):
        return text
    return "\n".join(lines[1:-1]).strip()


async def ensure_session_titles(workspace_id: UUID, sessions: list[dict]) -> dict[str, str]:
    if not sessions:
        return {}

    pool = get_pool()
    session_ids = [s["session_id"] for s in sessions]
    cache_rows = await pool.fetch(
        "SELECT session_id, title, source_hash FROM session_titles "
        "WHERE workspace_id = $1 AND session_id = ANY($2::text[])",
        workspace_id,
        session_ids,
    )
    cached = {r["session_id"]: dict(r) for r in cache_rows}

    stale = []
    for session in sessions:
        source_hash = _source_hash(session)
        cached_row = cached.get(session["session_id"])
        if not cached_row or cached_row["source_hash"] != source_hash:
            stale.append({**session, "source_hash": source_hash})

    for i in range(0, len(stale), MAX_BATCH_SIZE):
        batch = stale[i : i + MAX_BATCH_SIZE]
        candidates = await _build_candidates(workspace_id, batch)
        titles = await _generate_titles(candidates)
        rows = [
            (workspace_id, c["session_id"], titles[c["session_id"]], c["source_hash"])
            for c in candidates
        ]
        await pool.executemany(
            "INSERT INTO session_titles (workspace_id, session_id, title, source_hash) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (workspace_id, session_id) DO UPDATE SET "
            "title = EXCLUDED.title, source_hash = EXCLUDED.source_hash, updated_at = now()",
            rows,
        )
        for workspace_id_value, session_id, title, source_hash in rows:
            cached[session_id] = {
                "workspace_id": workspace_id_value,
                "session_id": session_id,
                "title": title,
                "source_hash": source_hash,
            }

    return {session_id: cached[session_id]["title"] for session_id in session_ids}


async def _build_candidates(workspace_id: UUID, sessions: list[dict]) -> list[dict]:
    return [
        {
            "session_id": session["session_id"],
            "source_hash": session["source_hash"],
            "source": await _session_source(workspace_id, session),
        }
        for session in sessions
    ]


async def _session_source(workspace_id: UUID, session: dict) -> str:
    summary = _clean_text(session.get("stash_summary") or "")
    if summary:
        return summary[:MAX_SOURCE_CHARS]

    pool = get_pool()
    rows = await pool.fetch(
        "SELECT event_type, tool_name, content FROM history_events "
        "WHERE workspace_id = $1 AND session_id = $2 AND content <> '' "
        "ORDER BY created_at ASC, id ASC LIMIT 14",
        workspace_id,
        session["session_id"],
    )
    parts = []
    for row in rows:
        label = row["event_type"] or "event"
        if row["tool_name"]:
            label = f"{label}:{row['tool_name']}"
        content = _clean_text(row["content"] or "")
        if content:
            parts.append(f"{label}: {content[:500]}")
    return "\n".join(parts)[:MAX_SOURCE_CHARS]


async def _generate_titles(candidates: list[dict]) -> dict[str, str]:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is required to generate session titles")

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    payload = [{"session_id": c["session_id"], "source": c["source"]} for c in candidates]
    response = await client.messages.create(
        model=settings.SESSION_TITLE_MODEL,
        max_tokens=900,
        system=(
            "Write concise labels for coding agent sessions. Each label should be "
            "specific, 3 to 8 words, and must not include session IDs, agent IDs, "
            "hashes, or the word 'session'. Return raw JSON only, with no markdown."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    "Return a JSON array of objects shaped like "
                    '{"session_id": "...", "title": "..."}. Sessions:\n' + json.dumps(payload)
                ),
            }
        ],
    )
    text = "\n".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    parsed = json.loads(_json_text(text))
    titles = {item["session_id"]: _clean_text(item["title"]) for item in parsed}
    missing = [c["session_id"] for c in candidates if c["session_id"] not in titles]
    if missing:
        raise ValueError(f"Missing generated titles for sessions: {', '.join(missing)}")
    return titles
