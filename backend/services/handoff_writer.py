"""Stash handoff writer.

A new coding agent landing on a stash should be able to read one document
that orients them — what's here, what's going on, where to start, and the
human-written Stash Description. The writer agent maintains that document.

Design:
- One global cadence and one global toolset. Zero per-stash config.
- Inputs are gathered deterministically in code, then the SDK-backed
  agent loop is allowed to use the same toolset ask-the-stash uses to
  dig deeper. Hard caps prevent unbounded cost.
- Pin state freezes the doc when a human edits it; unpin resumes writing.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from ..database import get_pool
from . import agent_runtime, prompts

logger = logging.getLogger(__name__)

PER_REGEN_TIMEOUT = 300.0
MAX_TURNS = 8
MAX_OUTPUT_TOKENS = 4096


# --- Stale marking ---------------------------------------------------------


async def mark_stale(workspace_id: UUID) -> None:
    """Upsert the handoff row and mark it stale.

    Called from every write path that touches stash content. Idempotent.
    If we miss a call site, the consequence is only a slightly stale
    handoff — never data corruption.
    """
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO stash_handoffs (workspace_id, stale, stale_marked_at)
        VALUES ($1, TRUE, now())
        ON CONFLICT (workspace_id) DO UPDATE
            SET stale = TRUE,
                stale_marked_at = COALESCE(stash_handoffs.stale_marked_at, now())
        """,
        workspace_id,
    )


def mark_stale_bg(workspace_id: UUID) -> None:
    """Fire-and-forget wrapper that logs errors instead of swallowing them."""

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.warning("mark_stale failed for %s: %s", workspace_id, exc)

    task = asyncio.create_task(mark_stale(workspace_id))
    task.add_done_callback(_on_done)


# --- Reads -----------------------------------------------------------------


async def get_handoff(workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT workspace_id, body_markdown, model, input_tokens, output_tokens, "
        "turns_used, tool_calls_used, generated_at, stale, stale_marked_at, "
        "last_attempt_at, last_error, consecutive_failures, pinned_at, pinned_by "
        "FROM stash_handoffs WHERE workspace_id = $1",
        workspace_id,
    )
    return dict(row) if row else None


async def get_handoff_metadata(workspace_id: UUID) -> dict | None:
    """Lightweight query for the overview response — only the fields the
    frontend needs to decide whether to render the panel."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT body_markdown, generated_at, stale, pinned_at "
        "FROM stash_handoffs WHERE workspace_id = $1",
        workspace_id,
    )
    return dict(row) if row else None


# --- Pin / unpin / edit ----------------------------------------------------


async def edit_and_pin(workspace_id: UUID, body_markdown: str, user_id: UUID) -> None:
    """Editing implicitly pins. The writer worker skips pinned rows."""
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO stash_handoffs (workspace_id, body_markdown, pinned_at, pinned_by, stale)
        VALUES ($1, $2, now(), $3, FALSE)
        ON CONFLICT (workspace_id) DO UPDATE
            SET body_markdown = EXCLUDED.body_markdown,
                pinned_at = now(),
                pinned_by = EXCLUDED.pinned_by,
                stale = FALSE
        """,
        workspace_id,
        body_markdown,
        user_id,
    )


async def unpin(workspace_id: UUID) -> None:
    """Clear pin state and reset generated_at so the worker bypasses the
    24h gap and rewrites from scratch on its next eligible tick. The body
    is preserved until the worker overwrites — so the user sees their
    edited text until the writer runs."""
    pool = get_pool()
    await pool.execute(
        """
        UPDATE stash_handoffs
        SET pinned_at = NULL,
            pinned_by = NULL,
            generated_at = NULL,
            stale = TRUE,
            stale_marked_at = now() - INTERVAL '1 hour'
        WHERE workspace_id = $1
        """,
        workspace_id,
    )


# --- Seed gathering --------------------------------------------------------


async def _gather_seed(workspace_id: UUID) -> prompts.HandoffSeed:
    pool = get_pool()

    ws = await pool.fetchrow("SELECT name, description FROM workspaces WHERE id = $1", workspace_id)
    workspace_name = (ws and ws["name"]) or "stash"
    description = ws["description"] if ws else None

    sessions = await pool.fetch(
        "SELECT session_id, agent_name, finished_at, started_at, summary "
        "FROM sessions WHERE workspace_id = $1 "
        "ORDER BY COALESCE(finished_at, started_at) DESC NULLS LAST "
        "LIMIT 10",
        workspace_id,
    )
    sessions_out: list[dict] = []
    for s in sessions:
        sessions_out.append(
            {
                "session_id": s["session_id"],
                "agent_name": s["agent_name"] or "",
                "last_at": (
                    (s["finished_at"] or s["started_at"]).isoformat()
                    if (s["finished_at"] or s["started_at"])
                    else None
                ),
                "summary": s["summary"] or "",
            }
        )

    pages = await pool.fetch(
        "SELECT id, name FROM pages "
        "WHERE workspace_id = $1 AND folder_id IS NULL "
        "ORDER BY updated_at DESC LIMIT 50",
        workspace_id,
    )
    pages_out = [{"page_id": str(p["id"]), "name": p["name"]} for p in pages]

    file_counts_rows = await pool.fetch(
        "SELECT COALESCE(content_type, 'unknown') AS ct, COUNT(*)::INT AS n "
        "FROM files WHERE workspace_id = $1 "
        "GROUP BY content_type ORDER BY n DESC",
        workspace_id,
    )
    file_counts = {r["ct"]: r["n"] for r in file_counts_rows}

    recent_files_rows = await pool.fetch(
        "SELECT name FROM files WHERE workspace_id = $1 " "ORDER BY created_at DESC LIMIT 20",
        workspace_id,
    )
    recent_files = [r["name"] for r in recent_files_rows]

    activity_rows = await pool.fetch(
        """
        SELECT event_type AS kind, content AS target_label, created_at AS ts,
               session_id AS target_id
        FROM history_events
        WHERE workspace_id = $1
          AND created_at >= now() - INTERVAL '14 days'
        ORDER BY created_at DESC
        LIMIT 30
        """,
        workspace_id,
    )
    activity = [
        {
            "kind": r["kind"],
            "target_label": (r["target_label"] or "")[:80],
            "target_id": r["target_id"],
            "ts": r["ts"].isoformat() if r["ts"] else None,
        }
        for r in activity_rows
    ]

    return prompts.HandoffSeed(
        workspace_name=workspace_name,
        description=description,
        sessions=sessions_out,
        pages=pages_out,
        file_counts=file_counts,
        recent_files=recent_files,
        activity=activity,
    )


def _seed_fingerprint(seed: prompts.HandoffSeed) -> str:
    """SHA256 of the seed inputs. If unchanged, regenerate() short-circuits
    (no LLM call). The agent loop's exploration is dynamic, but the
    trigger to re-run is deterministic."""
    h = hashlib.sha256()
    h.update(seed.workspace_name.encode())
    if seed.description:
        h.update(seed.description.encode())
    for s in sorted(seed.sessions, key=lambda x: x.get("session_id") or ""):
        h.update(
            f"{s.get('session_id')}|{s.get('last_at')}|{(s.get('summary') or '')[:200]}".encode()
        )
    for p in sorted(seed.pages, key=lambda x: x.get("page_id") or ""):
        h.update(f"{p.get('page_id')}|{p.get('name')}".encode())
    for ct, n in sorted(seed.file_counts.items()):
        h.update(f"{ct}:{n}".encode())
    for fn in seed.recent_files:
        h.update(fn.encode())
    for ev in seed.activity:
        h.update(f"{ev.get('ts')}|{ev.get('kind')}|{ev.get('target_id')}".encode())
    return h.hexdigest()


# --- Regeneration ----------------------------------------------------------


async def _record_failure(workspace_id: UUID, error: str) -> None:
    pool = get_pool()
    await pool.execute(
        """
        UPDATE stash_handoffs
        SET consecutive_failures = consecutive_failures + 1,
            last_attempt_at = now(),
            last_error = $2
        WHERE workspace_id = $1
        """,
        workspace_id,
        error,
    )


async def _record_success(
    workspace_id: UUID,
    body: str,
    fingerprint: str,
    result: agent_runtime.AgentResult,
) -> None:
    pool = get_pool()
    last_error = (
        None if result.terminated_by == "end_turn" else f"loop terminated by {result.terminated_by}"
    )
    await pool.execute(
        """
        UPDATE stash_handoffs
        SET body_markdown = $2,
            input_fingerprint = $3,
            model = $4,
            input_tokens = $5,
            output_tokens = $6,
            turns_used = $7,
            tool_calls_used = $8,
            generated_at = now(),
            stale = FALSE,
            last_attempt_at = now(),
            last_error = $9,
            consecutive_failures = 0
        WHERE workspace_id = $1
        """,
        workspace_id,
        body,
        fingerprint,
        result.model,
        result.input_tokens,
        result.output_tokens,
        result.turns_used,
        result.tool_calls_used,
        last_error,
    )


async def _clear_stale_only(workspace_id: UUID, fingerprint: str) -> None:
    """Fingerprint short-circuit: nothing meaningful changed since last
    successful run. Just clear stale without spending tokens."""
    pool = get_pool()
    await pool.execute(
        """
        UPDATE stash_handoffs
        SET stale = FALSE,
            last_attempt_at = now(),
            last_error = NULL,
            consecutive_failures = 0,
            input_fingerprint = $2
        WHERE workspace_id = $1
        """,
        workspace_id,
        fingerprint,
    )


async def regenerate(workspace_id: UUID) -> None:
    """Re-write the handoff for this stash. Synchronous; the caller (worker
    tick, regenerate endpoint) wraps in an advisory lock + wall-clock
    timeout."""
    seed = await _gather_seed(workspace_id)
    fingerprint = _seed_fingerprint(seed)

    existing = await get_handoff(workspace_id)
    if (
        existing
        and existing["input_fingerprint"] == fingerprint
        and existing["body_markdown"]
        and existing["generated_at"] is not None
    ):
        await _clear_stale_only(workspace_id, fingerprint)
        logger.info(
            "handoff writer: fingerprint unchanged for %s — skipped LLM call",
            workspace_id,
        )
        return

    seed_text = prompts.render_handoff_seed(seed)
    started = datetime.now(UTC)
    try:
        result = await agent_runtime.run_agent(
            tier=agent_runtime.ModelTier.QUALITY,
            system=prompts.HANDOFF_WRITER_SYSTEM,
            prompt=seed_text,
            stash_id=workspace_id,
            tool_set=prompts.STASH_TOOL_SET,
            max_turns=MAX_TURNS,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except Exception as exc:
        logger.exception("handoff writer failed for %s: %s", workspace_id, exc)
        await _record_failure(workspace_id, f"{type(exc).__name__}: {exc}")
        return

    body = (result.text or "").strip()
    if not body:
        await _record_failure(
            workspace_id,
            f"loop produced no text (terminated_by={result.terminated_by}, "
            f"turns={result.turns_used}, tool_calls={result.tool_calls_used})",
        )
        return

    await _record_success(workspace_id, body, fingerprint, result)
    latency = (datetime.now(UTC) - started).total_seconds()
    logger.info(
        "handoff writer: regenerated %s (%s, turns=%d, tool_calls=%d, "
        "in=%d out=%d, %.1fs, terminated_by=%s)",
        workspace_id,
        result.model,
        result.turns_used,
        result.tool_calls_used,
        result.input_tokens,
        result.output_tokens,
        latency,
        result.terminated_by,
    )


def seed_to_dict(seed: prompts.HandoffSeed) -> dict:
    """Test helper — exposes the seed shape without leaking internals."""
    return asdict(seed)
