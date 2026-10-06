"""Project native coding-session uploads into the owner's reviewable traces.

Live transcript snapshots only append: retries and older snapshots must not
erase steps, review comments, or saved action scores.
"""

from uuid import UUID

from ...database import get_pool
from ..session_title_service import title_from_text
from ..transcript_import import _decompress
from . import traces
from .adapters import TraceFormatError, parse_traces


def _step_values(step) -> tuple:
    return (
        step.role,
        step.content,
        step.tool_name,
        step.tool_input,
        step.tool_call_id,
        step.metadata or None,
    )


async def sync_transcript(owner: UUID, session_id: str, body: bytes) -> dict:
    source_format, parsed = parse_traces(_decompress(body), "auto")
    if source_format not in {"codex", "claude_code"} or len(parsed) != 1:
        raise TraceFormatError("Live trace sync supports Codex and Claude Code transcripts")
    trace = parsed[0]
    if trace.external_id != session_id:
        raise TraceFormatError("Transcript session id does not match the upload session id")
    trace.external_id = session_id
    trace.metadata.update({"session_id": session_id, "agent": source_format, "domain": "coding"})
    columns = ("role", "content", "tool_name", "tool_input", "tool_call_id", "metadata")
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))", f"rm_session:{owner}:{session_id}"
        )
        existing = await conn.fetchrow(
            "SELECT id FROM rm_traces WHERE owner_user_id = $1 AND external_id = $2 FOR UPDATE",
            owner,
            session_id,
        )
        if existing is None:
            trace.title = (
                trace.title
                or await conn.fetchval(
                    "SELECT title FROM sessions WHERE owner_user_id = $1 AND session_id = $2",
                    owner,
                    session_id,
                )
                or title_from_text(
                    next((s.content for s in trace.steps if s.role == "user"), None), session_id
                )
            )
            ids = await traces.store_traces(conn, owner, source_format, [trace])
            return {"id": ids[0], "appended": len(trace.steps)}
        trace_id = existing["id"]
        stored = await conn.fetch(
            "SELECT role, content, tool_name, tool_input, tool_call_id, metadata "
            "FROM rm_trace_steps WHERE trace_id = $1 ORDER BY idx",
            trace_id,
        )
        for old, new in zip(stored, trace.steps):
            if tuple(old[key] for key in columns) != _step_values(new):
                raise TraceFormatError(
                    "Transcript differs from previously uploaded steps; existing review preserved"
                )
        if len(trace.steps) <= len(stored):
            return {"id": trace_id, "appended": 0}
        await conn.executemany(
            "INSERT INTO rm_trace_steps "
            "(trace_id, idx, role, content, tool_name, tool_input, tool_call_id, metadata) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            [
                (trace_id, idx, *_step_values(step))
                for idx, step in enumerate(trace.steps[len(stored) :], start=len(stored))
            ],
        )
        # Updating recency queues automatic scoring and invalidates stale training
        # contributions through the existing trace-change trigger.
        await conn.execute("UPDATE rm_traces SET updated_at = now() WHERE id = $1", trace_id)
        return {"id": trace_id, "appended": len(trace.steps) - len(stored)}
