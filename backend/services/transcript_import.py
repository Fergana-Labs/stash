"""Parse a raw agent transcript (JSONL, optionally gzipped) into the event
shape `memory_service.push_events_batch` expects.

The CLI writes a JSONL line per turn. Each line is shaped roughly:

    {"type": "user" | "assistant", "message": {"content": "string" or
     [{"type": "text"|"tool_use"|"tool_result", ...}]}, "timestamp": "...",
     "uuid": "...", ...}

We map each line to a session event row so the session viewer can
reconstruct the conversation by querying rows ordered by created_at.

Reuses the parsing pattern from `routers/skills.py:get_skill_transcript_messages`
but goes one step further by also surfacing tool_use blocks as their own
events.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def _decompress(blob: bytes) -> str:
    if blob[:2] == b"\x1f\x8b":
        blob = gzip.decompress(blob)
    return blob.decode("utf-8", errors="replace")


def _parse_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        # Tolerate Z suffix and missing tz
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _text_from_content(content: Any) -> str:
    """Pull the human-readable text out of a content field.

    Anthropic-format content can be a string, or a list of content blocks
    (text / tool_use / tool_result). We concatenate the text blocks; tool
    blocks are surfaced as their own events upstream.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("text", "input_text", "output_text"):
            txt = block.get("text", "")
            if isinstance(txt, str) and txt.strip():
                parts.append(txt)
    return "\n\n".join(parts)


def _content_repr(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _tool_blocks(content: Any) -> list[dict]:
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]


def _parse_codex_response_item(obj: dict, *, session_id: str, agent_name: str) -> list[dict]:
    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
    payload_type = payload.get("type")
    created_at = _parse_ts(obj.get("timestamp")) or _parse_ts(payload.get("timestamp"))

    if payload_type == "message":
        role = payload.get("role")
        if role not in ("user", "assistant"):
            return []
        text_content = _text_from_content(payload.get("content", ""))
        if not text_content.strip():
            return []
        return [
            {
                "agent_name": agent_name,
                "event_type": "user_message" if role == "user" else "assistant_message",
                "content": text_content,
                "session_id": session_id,
                "tool_name": None,
                "metadata": {"source": "transcript_import"},
                "created_at": created_at,
            }
        ]

    if payload_type == "function_call":
        return [
            {
                "agent_name": agent_name,
                "event_type": "tool_use",
                "content": _content_repr(payload.get("arguments")),
                "session_id": session_id,
                "tool_name": payload.get("name") or None,
                "metadata": {"source": "transcript_import"},
                "created_at": created_at,
            }
        ]

    if payload_type == "function_call_output":
        return [
            {
                "agent_name": agent_name,
                "event_type": "tool_result",
                "content": _content_repr(payload.get("output")),
                "session_id": session_id,
                "tool_name": None,
                "metadata": {"source": "transcript_import"},
                "created_at": created_at,
            }
        ]

    return []


def parse_jsonl_to_events(
    blob: bytes,
    *,
    session_id: str,
    agent_name: str,
) -> list[dict]:
    """Parse a transcript blob into event dicts ready for push_events_batch.

    Each event dict has: agent_name, event_type, content, session_id,
    tool_name, metadata, created_at, source_uuid. Caller supplies
    owner_user_id and created_by when calling push_events_batch.

    source_uuid is deterministic per line (the line's own uuid when present,
    a hash of the line otherwise) so re-uploading the same transcript
    conflicts on the unique index instead of duplicating rows. A message
    Claude re-serializes under a *new* uuid after compaction still gets a
    new id — content-based dedup is deliberately not attempted, since it
    can't match across the live/import representations and would collapse
    genuinely repeated messages.
    """
    text = _decompress(blob)
    events: list[dict] = []
    for line_idx, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue

        line_events: list[dict] = []
        entry_type = obj.get("type")
        if entry_type == "response_item":
            line_events = _parse_codex_response_item(
                obj, session_id=session_id, agent_name=agent_name
            )
        elif entry_type in ("user", "assistant"):
            message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
            content_raw = message.get("content", "")
            text_content = _text_from_content(content_raw)
            created_at = _parse_ts(obj.get("timestamp")) or _parse_ts(message.get("timestamp"))

            if text_content.strip():
                line_events.append(
                    {
                        "agent_name": agent_name,
                        "event_type": "user_message"
                        if entry_type == "user"
                        else "assistant_message",
                        "content": text_content,
                        "session_id": session_id,
                        "tool_name": None,
                        "metadata": {"source": "transcript_import"},
                        "created_at": created_at,
                    }
                )

            # Surface tool_use blocks (assistant side) as their own events so
            # the timeline shows tool calls alongside messages — mirrors what
            # the live hook does.
            for tu in _tool_blocks(content_raw):
                tool_name = tu.get("name") or ""
                tool_input = tu.get("input")
                line_events.append(
                    {
                        "agent_name": agent_name,
                        "event_type": "tool_use",
                        "content": _content_repr(tool_input),
                        "session_id": session_id,
                        "tool_name": tool_name or None,
                        "metadata": {"source": "transcript_import"},
                        "created_at": created_at,
                    }
                )

        if not line_events:
            continue

        raw_uuid = obj.get("uuid")
        if isinstance(raw_uuid, str) and raw_uuid:
            base = raw_uuid
        else:
            # Codex lines carry no per-line id; transcript files are
            # append-only, so the line index is stable across re-uploads.
            base = hashlib.sha256(f"{session_id}:{line_idx}:{line}".encode()).hexdigest()
        for j, ev in enumerate(line_events):
            ev["source_uuid"] = f"{base}:{j}"
        events.extend(line_events)

    return events
