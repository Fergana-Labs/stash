"""Read public Codex turns without importing the history corpus into Stash.

Discovery deliberately over-retrieves. Its records are candidates, never labels.
Artifacts are recovered only from complete recorded writes and successful tool
receipts, never by reading today's working tree or executing historical commands.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path

MAX_LINE = 4 * 1024 * 1024
WEBSITE = re.compile(
    r"\b(website|landing[ -]page|web[ -]?page|homepage|web[ -]design|redesign|frontend|front.end|css|typography)\b",
    re.I,
)
TASTE = re.compile(
    r"\b(font|typography|spacing|colou?r|contrast|layout|design|ugly|looks?|rounded|visual|padding|margin|gradient|hero|whitespace|slop|taste|style)\b",
    re.I,
)
SKIP = ("# AGENTS.md", "<environment_context>", "<permissions instructions>")


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def rows(path: Path):
    """Bounded line reads: malformed/oversize rows yield explicit coverage markers."""
    with path.open("rb") as stream:
        number = 0
        while line := stream.readline(MAX_LINE + 1):
            number += 1
            if len(line) > MAX_LINE:
                while line and not line.endswith(b"\n"):
                    line = stream.readline(MAX_LINE + 1)
                yield number, {"type": "unreadable", "reason": "oversize_row"}
                continue
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    yield number, row
            except (ValueError, UnicodeError):
                yield number, {"type": "unreadable", "reason": "malformed_row"}


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        part.get("text", "")
        for part in content
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    )


def public_events(path: Path):
    """One canonical public stream, with stable raw-line references for provenance."""
    for line, row in rows(path):
        payload = row.get("payload") or {}
        if row.get("type") == "unreadable":
            yield {"line": line, "kind": "unreadable", "reason": row["reason"]}
        if row.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        kind = payload.get("type")
        if kind == "message" and payload.get("role") in ("user", "assistant"):
            text = text_of(payload.get("content"))
            images = []
            for part in payload.get("content") or []:
                if not isinstance(part, dict):
                    continue
                url = part.get("image_url")
                if isinstance(url, dict):
                    url = url.get("url")
                if isinstance(url, str) and url.startswith("data:image/"):
                    images.append(url)
            if (text or images) and not text.lstrip().startswith(SKIP):
                yield {
                    "line": line,
                    "kind": "message",
                    "role": payload["role"],
                    "text": text,
                    "images": images,
                }
        elif kind in ("function_call", "custom_tool_call"):
            yield {
                "line": line,
                "kind": "call",
                "name": payload.get("name", ""),
                "call_id": payload.get("call_id"),
                "arguments": payload.get("arguments", payload.get("input", "")),
            }
        elif kind in ("function_call_output", "custom_tool_call_output"):
            output = payload.get("output")
            yield {
                "line": line,
                "kind": "result",
                "call_id": payload.get("call_id"),
                "output": output if isinstance(output, str) else json.dumps(output),
            }


def discover(home: Path, output: Path, *, exclude: set[str] | None = None) -> dict:
    roots = [home / ".codex" / name for name in ("sessions", "archived_sessions")]
    output.mkdir(parents=True, exist_ok=True)
    excluded = (exclude or set()) | {os.getenv("CODEX_THREAD_ID", "")}
    candidates, seen = [], set()
    coverage = {"files": 0, "sessions": 0, "unreadable_rows": 0, "skipped_files": 0}
    with (output / "candidates.jsonl").open("w") as out:
        for root in roots:
            for path in sorted(root.rglob("*.jsonl")):
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                    coverage["skipped_files"] += 1
                    continue
                coverage["files"] += 1
                try:
                    _, first = next(rows(path))
                    meta = first.get("payload") or {}
                    sid = meta.get("id")
                    if first.get("type") != "session_meta" or not sid or sid in seen:
                        continue
                    seen.add(sid)
                    coverage["sessions"] += 1
                    if sid in excluded:
                        continue
                    title, matches, feedback, writes = "", [], [], 0
                    for event in public_events(path):
                        if event["kind"] == "unreadable":
                            coverage["unreadable_rows"] += 1
                        if event["kind"] == "call":
                            args = str(event["arguments"])
                            writes += int(
                                ".html" in args
                                and any(
                                    t in args
                                    for t in ("*** Add File", "cat ", "write_text", "writeFile")
                                )
                            )
                        if event["kind"] != "message" or event["role"] != "user":
                            continue
                        text = event["text"]
                        if not title:
                            title = text.splitlines()[0][:180]
                        if WEBSITE.search(text) and len(matches) < 8:
                            matches.append(
                                {
                                    "line": event["line"],
                                    "text": text[:1600],
                                    "clipped": len(text) > 1600,
                                }
                            )
                        if TASTE.search(text) and len(feedback) < 30:
                            feedback.append(
                                {
                                    "line": event["line"],
                                    "text": text[:2400],
                                    "clipped": len(text) > 2400,
                                }
                            )
                    if matches:
                        record = {
                            "session_id": sid,
                            "path": str(path),
                            "project": meta.get("cwd", ""),
                            "started_at": meta.get("timestamp", first.get("timestamp")),
                            "history_base": meta.get("history_base"),
                            "title": title,
                            "website_mentions": matches,
                            "possible_feedback": feedback,
                            "possible_html_writes": writes,
                            "status": "candidate",
                            "source_size": path.stat().st_size,
                        }
                        out.write(json.dumps(record) + "\n")
                        candidates.append(record)
                except (OSError, ValueError, StopIteration):
                    coverage["skipped_files"] += 1
                if coverage["files"] % 100 == 0:
                    print(
                        json.dumps(
                            {"phase": "discover", **coverage, "candidates": len(candidates)}
                        ),
                        flush=True,
                    )
    report = {
        **coverage,
        "candidates": len(candidates),
        "candidate_sessions_with_html_writes": sum(
            bool(c["possible_html_writes"]) for c in candidates
        ),
        "source": "local_codex",
        "includes_recorded_stash": False,
        "labels_inferred": False,
        "private_reasoning_included": False,
        "resumed_histories_expanded": False,
    }
    (output / "coverage.json").write_text(json.dumps(report, indent=2))
    return report


def patch_additions(patch: str) -> list[tuple[str, str]]:
    """Only full Add File records; partial diffs cannot reconstruct earlier pixels."""
    additions, name, lines = [], None, []
    for line in patch.splitlines():
        if line.startswith("*** "):
            if name is not None:
                additions.append((name, "\n".join(lines) + "\n"))
            name, lines = None, []
            if line.startswith("*** Add File: "):
                name = line.removeprefix("*** Add File: ")
        elif name is not None:
            if not line.startswith("+"):
                name, lines = None, []
            else:
                lines.append(line[1:])
    if name is not None:
        additions.append((name, "\n".join(lines) + "\n"))
    return additions


def complete_writes(event: dict) -> list[tuple[str, str]]:
    """Parse literal heredocs/add-file patches; never evaluate Python, JS, or shell."""
    args = event["arguments"]
    # Codex's orchestration tool often wraps a literal patch in JavaScript.
    # Decode only a complete, single-call wrapper. Never execute the wrapper.
    if isinstance(args, str) and event["name"] == "exec":
        literal = re.fullmatch(
            r'\s*text\(await tools\.apply_patch\(("(?:[^"\\]|\\.)*")\)\);?\s*', args
        )
        if literal:
            return patch_additions(json.loads(literal[1]))
    if event["name"].split(".")[-1] == "apply_patch" and isinstance(args, str):
        return patch_additions(args)
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return []
    if not isinstance(args, dict) or not isinstance(args.get("cmd"), str):
        return []
    command = args["cmd"]
    # An entire literal shell write, not a quoted shell command embedded in code.
    match = re.fullmatch(
        r"\s*cat\s*>\s*(?P<path>[^\s<>|;&]+)\s*<<\s*'(?P<tag>[A-Za-z_][A-Za-z_0-9]*)'\s*\n(?P<body>[\s\S]*?)\n(?P=tag)\s*",
        command,
    )
    return [(match["path"], match["body"] + "\n")] if match else []


def recover(candidate: dict, output: Path) -> dict:
    """Save HTML states with their exact receipt and human feedback boundaries."""
    path = Path(candidate["path"])
    roots = [Path.home() / ".codex" / n for n in ("sessions", "archived_sessions")]
    if path.is_symlink() or not any(path.resolve().is_relative_to(r.resolve()) for r in roots):
        raise ValueError("Transcript must be inside local Codex history")
    output.mkdir(parents=True, exist_ok=True)
    pending, artifacts, users, screenshots = {}, [], [], []
    for event in public_events(path):
        if event["kind"] == "message" and event["role"] == "user":
            users.append({"line": event["line"], "text": event["text"]})
            for index, image in enumerate(event["images"]):
                match = re.fullmatch(
                    r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)", image
                )
                if not match:
                    continue
                try:
                    data = base64.b64decode(match[2], validate=False)
                except ValueError:
                    continue
                sha = digest(data)
                file = output / f"{sha}.{match[1]}"
                file.write_bytes(data)
                screenshots.append(
                    {
                        "sha256": sha,
                        "file": str(file),
                        "line": event["line"],
                        "feedback": event["text"],
                        "session_id": candidate["session_id"],
                        "image_index": index + 1,
                        "image_count": len(event["images"]),
                        "kind": "recorded_user_attachment",
                        "label": None,
                    }
                )
        elif event["kind"] == "call" and event.get("call_id"):
            writes = complete_writes(event)
            if writes:
                pending[event["call_id"]] = (event, writes)
        elif event["kind"] == "result" and event["call_id"] in pending:
            call, writes = pending.pop(event["call_id"])
            receipt = event["output"]
            success = (
                (
                    "Success. Updated the following files:" in receipt
                    or (
                        call["name"] == "exec"
                        and "Script completed" in receipt
                        and '"text": "{}"' in receipt
                    )
                )
                if call["name"].split(".")[-1] in ("apply_patch", "exec")
                else "Process exited with code 0" in receipt
                or '"exit_code":0' in receipt.replace(" ", "")
            ) and not re.search(r"\b(error|failed|isError)\b", receipt, re.I)
            if not success:
                continue
            for name, html in writes:
                if not name.lower().endswith((".html", ".htm")) or not re.search(
                    r"<!doctype\s+html|<html[\s>]", html, re.I
                ):
                    continue
                sha = digest(html)
                artifact = output / f"{sha}.html"
                artifact.write_text(html)
                artifacts.append(
                    {
                        "sha256": sha,
                        "file": str(artifact),
                        "original_path": name,
                        "call_line": call["line"],
                        "receipt_line": event["line"],
                        "session_id": candidate["session_id"],
                        "project": candidate["project"],
                        "brief": users[0] if users else None,
                        "preceding_user": users[-1] if users else None,
                        "kind": "complete_recorded_html_write",
                        "label": None,
                    }
                )
    # Exact next human turn, not a fabricated approval inferred from a later edit.
    for artifact in artifacts:
        artifact["next_user"] = next(
            (u for u in users if u["line"] > artifact["receipt_line"]), None
        )
    return {
        "session_id": candidate["session_id"],
        "project": candidate["project"],
        "artifacts": artifacts,
        "screenshots": screenshots,
        "human_turns": users,
        "partial_history": bool(candidate.get("history_base")),
        "labels_inferred": False,
    }
