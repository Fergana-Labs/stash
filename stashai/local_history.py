"""Read-only, bounded Codex history access for an authenticated local connector.

Requests select discovered session IDs, never filesystem paths or commands.
Only requested excerpts leave the machine; the corpus is not imported.
"""

from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path
from uuid import UUID

from stashai.plugin.codex_transcript import read_transcript

MAX_RESULT = 10_000
MAX_ASSET_RESULT = 6_000_000


def validate_request(operation: str, args: dict) -> dict:
    allowed = {
        "search": {"query", "agent", "offset", "limit", "event_offset"},
        "read": {"id", "offset", "limit"},
        "assets": {"id", "offset", "limit"},
    }
    if operation not in allowed or set(args) - allowed[operation]:
        raise ValueError("Unsupported history request")
    result = dict(args)
    for key, default, maximum in (
        ("offset", 0, 100_000),
        ("limit", 5 if operation == "search" else 20, 10 if operation == "search" else 40),
    ):
        value = result.get(key, default)
        if type(value) is not int or not (0 if key == "offset" else 1) <= value <= maximum:
            raise ValueError(f"Invalid history {key}")
        result[key] = value
    if operation == "search":
        event_offset = result.get("event_offset", 0)
        if type(event_offset) is not int or not 0 <= event_offset <= 1_000_000:
            raise ValueError("Invalid history event offset")
        result["event_offset"] = event_offset
        for key, maximum in (("query", 200), ("agent", 64)):
            value = result.get(key, "")
            if not isinstance(value, str) or len(value) > maximum:
                raise ValueError(f"Invalid history {key}")
            result[key] = value.strip()
    else:
        value = result.get("id")
        if not isinstance(value, str) or not value or len(value) > 128:
            raise ValueError("Invalid local session ID")
        try:
            UUID(value)
        except ValueError as exc:
            raise ValueError("Invalid history session ID") from exc
    return result


def bound_search(result: dict) -> dict:
    """Preserve every source ID and cursor even when preview text must shrink."""
    for length in (160, 60, 0):
        if len(json.dumps(result, default=str)) <= MAX_RESULT:
            break
        result["previews_truncated"] = True
        for row in result["results"]:
            for key in ("title", "snippet", "project"):
                if isinstance(row.get(key), str):
                    row[key] = row[key][:length]
    if len(json.dumps(result, default=str)) > MAX_RESULT:
        result["results"] = [
            {k: r[k] for k in ("kind", "id", "match_offset") if k in r} for r in result["results"]
        ]
    return result


def pack_page(source: dict, events, offset: int, limit: int) -> dict:
    """Keep complete JSON within the wizard tool budget, with explicit clipping."""
    result = {"source": source, "events": [], "offset": offset, "total": 0}
    stopped = False
    for index, event in enumerate(events):
        result["total"] = index + 1
        if not source.get("title") and event["role"] == "user":
            source["title"] = str(event.get("content") or "").split("\n", 1)[0][:160]
        if index < offset or stopped:
            continue
        content = str(event.get("content") or "")
        entry = {"index": index, "role": event["role"], "content": content[:3000]}
        if event.get("tool_name"):
            entry["tool_name"] = str(event["tool_name"])[:120]
        if len(content) > 3000:
            entry["content_truncated"] = True
        candidate = {**result, "events": [*result["events"], entry]}
        if not result["events"]:
            while len(json.dumps(candidate)) > MAX_RESULT - 1000 and len(entry["content"]) > 64:
                entry["content"] = entry["content"][: len(entry["content"]) // 2]
                entry["content_truncated"] = True
        if len(result["events"]) >= limit or len(json.dumps(candidate)) > MAX_RESULT - 1000:
            stopped = True
            continue
        result["events"].append(entry)
    result["next_offset"] = offset + len(result["events"])
    result["has_more"] = result["next_offset"] < result["total"]
    result["content_truncated"] = any(e.get("content_truncated") for e in result["events"])
    while len(json.dumps(result)) > MAX_RESULT and result["events"]:
        longest = max(result["events"], key=lambda e: len(e["content"]))
        if len(longest["content"]) <= 64:
            raise ValueError("History source metadata exceeds the excerpt budget")
        longest["content"] = longest["content"][: len(longest["content"]) // 2]
        longest["content_truncated"] = result["content_truncated"] = True
    return result


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            b.get("text", "")
            if b.get("type") in ("text", "input_text", "output_text")
            else "[Non-text attachment]"
            for b in value
            if isinstance(b, dict)
        )
    return ""


def _events(path: Path, raw: bytes | None = None):
    """Stream public conversation turns and tools; never private reasoning."""
    with io.BytesIO(raw) if raw is not None else path.open("rb") as file:
        while raw := file.readline(2 * 1024 * 1024 + 1):
            if not raw.endswith(b"\n") and len(raw) > 2 * 1024 * 1024:
                while tail := file.readline(2 * 1024 * 1024):
                    if tail.endswith(b"\n"):
                        break
                yield {"role": "tool", "content": "[Oversized Codex record omitted]"}
                continue
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(row, dict):
                continue
            payload = row.get("payload") or {}
            if row.get("type") != "response_item" or not isinstance(payload, dict):
                continue
            kind = payload.get("type")
            if kind == "message" and payload.get("role") in ("user", "assistant"):
                text = _text(payload.get("content"))
                if text.startswith(("# AGENTS.md instructions", "<environment_context>")):
                    continue
                if text:
                    yield {"role": payload["role"], "content": text}
            elif kind in ("function_call", "custom_tool_call"):
                yield {
                    "role": "assistant",
                    "tool_name": payload.get("name"),
                    "content": str(payload.get("arguments") or payload.get("input") or ""),
                }
            elif kind in ("function_call_output", "custom_tool_call_output"):
                yield {"role": "tool", "content": _text(payload.get("output"))}


class CodexHistory:
    def __init__(self, home: Path | None = None):
        home = home or Path.home()
        self.roots = [home / ".codex" / name for name in ("sessions", "archived_sessions")]
        self._inventory: dict[str, dict] = {}
        self._refreshed = 0.0

    def _safe(self, path: Path) -> bool:
        return not path.is_symlink() and any(
            path.resolve().is_relative_to(root.resolve()) for root in self.roots
        )

    def _discover(self):
        if time.monotonic() - self._refreshed < 30:
            return
        found = {}
        for root in self.roots:
            for path in root.rglob("*.jsonl"):
                try:
                    if not self._safe(path):
                        continue
                    with path.open("rb") as file:
                        row = json.loads(file.readline(64 * 1024))
                    if row.get("type") != "session_meta":
                        continue
                    meta = row.get("payload") or {}
                    sid = meta.get("id")
                    if not isinstance(sid, str) or not sid or len(sid) > 128:
                        continue
                    sid = str(UUID(sid))
                    stat = path.stat()
                    item = {
                        "path": path,
                        "mtime": stat.st_mtime,
                        "id": sid,
                        "kind": "local",
                        "session_id": sid,
                        "agent": "codex",
                        "project": str(meta.get("cwd") or "")[:300],
                        "started_at": str(meta.get("timestamp") or row.get("timestamp") or "")[:80],
                        "partial_history": bool(meta.get("history_base")),
                    }
                    if sid not in found or found[sid]["mtime"] < item["mtime"]:
                        found[sid] = item
                except (OSError, ValueError, TypeError, AttributeError):
                    continue
        self._inventory = dict(
            sorted(found.items(), key=lambda pair: pair[1]["mtime"], reverse=True)
        )
        self._refreshed = time.monotonic()

    def run(self, operation: str, args: dict) -> dict:
        args = validate_request(operation, args)
        self._discover()
        if operation == "search":
            return self.search(**args)
        item = self._inventory.get(args["id"])
        if not item or not self._safe(item["path"]):
            raise ValueError("Local session not found")
        if operation == "assets":
            return self.assets(item, args["offset"], min(args["limit"], 2))
        source, events = self._open(item)
        return pack_page(source, events, args["offset"], args["limit"])

    def assets(self, item, offset, limit):
        """Embedded pixels only. No filesystem paths or arbitrary local files."""
        import base64
        import hashlib

        assets, tail, count, first = [], [], 0, None
        next_offset, has_more = offset, False
        image_cursor = 0
        with item["path"].open("rb") as stream:

            def bounded_lines():
                while raw := stream.readline(8_000_001):
                    if len(raw) > 8_000_000:
                        while not raw.endswith(b"\n"):
                            raw = stream.readline(8_000_001)
                            if not raw:
                                break
                        yield b""
                    else:
                        yield raw

            for line_index, raw in enumerate(bounded_lines()):
                if len(raw) > 8_000_000:
                    continue
                try:
                    row = json.loads(raw)
                except (ValueError, UnicodeError):
                    continue
                payload = row.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                content = payload.get("content") or []
                images = (
                    [
                        b.get("image_url", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "input_image"
                    ]
                    if isinstance(content, list)
                    else []
                )
                if payload.get("role") == "user" and row.get("type") == "response_item":
                    for index, uri in enumerate(images):
                        current = image_cursor
                        image_cursor += 1
                        if current < offset:
                            continue
                        next_offset = image_cursor
                        if not isinstance(uri, str) or not uri.startswith(
                            ("data:image/png;base64,", "data:image/jpeg;base64,")
                        ):
                            continue
                        try:
                            pixels = base64.b64decode(uri.split(",", 1)[1], validate=True)
                        except ValueError:
                            continue
                        if len(pixels) > 2_000_000:
                            continue
                        trace = ([first] if first and first not in tail else []) + tail
                        asset = {
                            "id": f"{item['id']}:{line_index}:{index + 1}",
                            "session_id": item["id"],
                            "line": line_index,
                            "image_index": index + 1,
                            "image_count": len(images),
                            "feedback": _text(content),
                            "sha256": hashlib.sha256(pixels).hexdigest(),
                            "image_base64": base64.b64encode(pixels).decode(),
                            "trace": {
                                "steps": trace,
                                "coverage": {
                                    "complete": not item["partial_history"] and count == len(trace),
                                    "selected_steps": len(trace),
                                    "public_steps_before_target": count,
                                    "target_feedback_excluded": True,
                                    "future_steps_excluded": True,
                                },
                            },
                        }
                        if (
                            len(assets) >= limit
                            or len(json.dumps({"assets": [*assets, asset]}))
                            > MAX_ASSET_RESULT - 1000
                        ):
                            return {"assets": assets, "next_offset": current, "has_more": True}
                        assets.append(asset)
                for event in _events(item["path"], raw):
                    normalized = {
                        "id": str(count),
                        "role": event["role"],
                        "text": event["content"][:2400],
                        "clipped": len(event["content"]) > 2400,
                    }
                    count += 1
                    if first is None and event["role"] == "user":
                        first = normalized
                    tail.append(normalized)
                    tail = tail[-8:]
        return {"assets": assets, "next_offset": next_offset, "has_more": has_more}

    def _open(self, item):
        source = {k: v for k, v in item.items() if k not in ("path", "mtime")}
        raw = None
        if item["partial_history"]:
            try:
                raw = read_transcript(item["path"], allowed_roots=self.roots)
                source["partial_history"] = False
            except (OSError, ValueError):
                source["history_warning"] = (
                    "Earlier resumed pages could not be resolved; this excerpt is from the current page only."
                )
        return source, _events(item["path"], raw)

    def search(
        self, query: str, agent: str, offset: int, limit: int, event_offset: int = 0
    ) -> dict:
        if agent and "codex" not in agent.lower():
            return {"results": [], "has_more": False, "next_offset": offset, "scanned": 0}
        terms = re.findall(r"[\w.-]+", query.casefold())
        items = list(self._inventory.values())
        results, scanned = [], 0
        deadline = time.monotonic() + 8
        resume_event = 0
        for item in items[offset:]:
            scanned += 1
            title = ""
            metadata_match = all(
                t in (item["project"] + " " + item["id"]).casefold() for t in terms
            )
            try:
                if not self._safe(item["path"]):
                    continue
                source, events = self._open(item)
                for index, event in enumerate(events):
                    if not title and event["role"] == "user":
                        title = event["content"].splitlines()[0][:160]
                    if scanned == 1 and index < event_offset:
                        continue
                    if metadata_match or all(t in event["content"].casefold() for t in terms):
                        results.append(
                            {
                                **source,
                                "title": title or item["id"],
                                "snippet": event["content"][:350],
                                "match_offset": index,
                            }
                        )
                        break
                    if time.monotonic() > deadline:
                        resume_event = index + 1
                        break
            except OSError:
                continue
            if len(results) >= limit or scanned >= 200 or time.monotonic() > deadline:
                break
        next_offset = offset + scanned - bool(resume_event)
        return bound_search(
            {
                "results": results,
                "scanned": scanned,
                "next_offset": next_offset,
                "next_event_offset": resume_event,
                "has_more": next_offset < len(items),
            }
        )
