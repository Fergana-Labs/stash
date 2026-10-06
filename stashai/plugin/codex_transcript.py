"""Resolve Codex's local paginated history before uploading a transcript.

A resumed rollout can contain only new records, with history_base pointing to
an exact prefix of an earlier file. Sending that page alone loses the prompt
and earlier tools. Resolve locally: the server cannot read these base files.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

MAX_BYTES = 128 * 1024 * 1024


def _meta(raw: bytes) -> dict:
    try:
        record = json.loads(raw.partition(b"\n")[0])
    except (ValueError, UnicodeError):
        return {}
    if isinstance(record, dict) and record.get("type") == "session_meta":
        return record
    return {}


def _roots(path: Path) -> list[Path]:
    for parent in path.parents:
        if parent.name in {"sessions", "archived_sessions"}:
            return [parent.parent / "sessions", parent.parent / "archived_sessions"]
    return [path.parent]


def _expand(path: Path, raw: bytes, roots: list[Path], seen: set[Path]) -> bytes:
    meta = _meta(raw)
    base = meta.get("payload", {}).get("history_base")
    if not base:
        return raw
    if path in seen or len(seen) >= 32:
        raise ValueError("Codex history_base contains a cycle or too many pages")
    seen = seen | {path}
    try:
        thread_id = str(UUID(base["thread_id"]))
        offset = base["end_byte_offset"]
        end = base["end_ordinal_exclusive"]
        if (
            type(offset) is not int
            or type(end) is not int
            or not 0 < offset <= MAX_BYTES
            or end < 1
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid Codex history_base boundary") from exc

    matched: tuple[Path, bytes] | None = None
    for root in roots:
        for candidate in root.rglob(f"*{thread_id}*.jsonl"):
            candidate = candidate.resolve()
            if candidate in seen or candidate.stat().st_size < offset:
                continue
            with candidate.open("rb") as file:
                header = _meta(file.readline())
                if header.get("payload", {}).get("id") != thread_id:
                    continue
                if header.get("ordinal", 0) >= end:
                    continue
                file.seek(0)
                prefix = file.read(offset)
            if not prefix.endswith(b"\n"):
                continue
            try:
                last = json.loads(prefix.rstrip(b"\r\n").rsplit(b"\n", 1)[-1])
            except (ValueError, UnicodeError):
                continue
            if not isinstance(last, dict) or last.get("ordinal") != end - 1:
                continue
            if matched and matched[1] != prefix:
                raise ValueError("Ambiguous Codex history_base; refusing to mix conversations")
            matched = (candidate, prefix)
    if matched is None:
        raise ValueError(
            f"Missing Codex history_base for {thread_id}; full transcript not uploaded"
        )

    parent = _expand(matched[0], matched[1], roots, seen)
    # Keep the current session's identity, including when it forked another
    # thread. Earlier session_meta headers are replaced, not sent as new turns.
    meta["payload"].pop("history_base", None)
    header = json.dumps(meta).encode() + b"\n"
    earlier = parent.partition(b"\n")[2]
    current = raw.partition(b"\n")[2]
    if len(header) + len(earlier) + len(current) > MAX_BYTES:
        raise ValueError("Reconstructed Codex transcript exceeds 128 MB")
    return header + earlier + current


def read_transcript(path: Path) -> bytes:
    """Read ordinary transcripts unchanged; inline any Codex history_base."""
    path = path.resolve()
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Transcript exceeds 128 MB")
    return _expand(path, path.read_bytes(), _roots(path), set())
