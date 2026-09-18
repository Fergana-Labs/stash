"""
Read a Claude Code session jsonl and produce seed_events.json for Arm B.

Approach:
1. Walk the jsonl and build a compact chronological narrative — filtering out
   attachments (skill listings, deferred tool deltas), thinking blocks, and
   raw tool results > 500 chars.
2. Send the narrative to Haiku with a prompt that asks for 20–40 seed events,
   each one an OBSERVATION about what Session A did/decided/found — not a
   prescription for how Session B should solve the task.
3. Print JSON to stdout.

Usage:
    python -m harness.extract_session SESSION_A.jsonl > seed_events.json
"""

from __future__ import annotations

import json
import os
import sys

from anthropic import Anthropic

MAX_TOOL_RESULT_CHARS = 500
EXTRACTOR_MODEL = os.environ.get("STASH_EVAL_EXTRACTOR_MODEL", "claude-haiku-4-5-20251001")


def walk_jsonl(path: str) -> list[dict]:
    """Read the jsonl and return parsed records."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def build_narrative(records: list[dict]) -> str:
    """Collapse the session into a skimmable transcript."""
    lines: list[str] = []
    for rec in records:
        rtype = rec.get("type")

        if rtype == "attachment":
            continue
        if rtype in ("file-history-snapshot", "permission-mode"):
            continue

        ts = rec.get("timestamp", "")
        msg = rec.get("message", {})

        if rtype == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                lines.append(f"[{ts}] USER: {content}")
                continue
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        body = block.get("content", "")
                        if isinstance(body, list):
                            body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                        body = str(body)[:MAX_TOOL_RESULT_CHARS]
                        lines.append(f"[{ts}] TOOL_RESULT: {body}")
            continue

        if rtype == "assistant":
            for block in msg.get("content", []):
                btype = block.get("type")
                if btype == "text":
                    txt = block.get("text", "").strip()
                    if txt:
                        lines.append(f"[{ts}] ASSISTANT: {txt}")
                elif btype == "tool_use":
                    tool = block.get("name", "?")
                    inp = block.get("input", {})
                    summary = summarize_tool_input(tool, inp)
                    lines.append(f"[{ts}] TOOL_USE {tool}: {summary}")
    return "\n".join(lines)


def summarize_tool_input(tool: str, inp: dict) -> str:
    """Short human-readable description of a tool call."""
    if tool in ("Read", "Glob"):
        return inp.get("file_path") or inp.get("pattern", "")
    if tool == "Grep":
        return f"pattern={inp.get('pattern', '')!r} path={inp.get('path', '')}"
    if tool == "Bash":
        return str(inp.get("command", ""))[:200]
    if tool in ("Edit", "Write"):
        return inp.get("file_path", "")
    return json.dumps(inp)[:200]


EXTRACT_PROMPT = """You are extracting seed events from a Claude Code session transcript. These events will be pushed to a shared history store so that a DIFFERENT agent, in a LATER session, can search them via `stash history search` and avoid rediscovering what this session already learned.

## Critical rules

1. Every event must be an OBSERVATION of what happened in this session ("Session A decided X", "Session A found the polling logic at cli/main.py:1045"). NOT a prescription telling a future agent what to do.

2. Aim for 20–40 events total. Each event's `text` field: 1–3 sentences, ~50–150 words.

3. Prefer events that encode *transferable* knowledge:
   - Architectural decisions and why
   - File/function locations for non-obvious code
   - Failed approaches (so future agents don't re-try)
   - Gotchas discovered
   - Design invariants established

4. SKIP: trivial file reads, session-specific chit-chat, unrelated tangents, "I will now edit X" narration.

5. For each event, pick a `type` from: decision, discovery, file_edit, failed_approach, gotcha, user_intent.

## Output

Return JSON only. No prose. Schema:

```
[
  {
    "type": "discovery",
    "text": "Session A found the existing browser-auth polling logic in cli/main.py at the `connect` command (around line 1045): webbrowser.open followed by polling /api/v1/users/cli-auth/sessions/{session_id}.",
    "tags": ["auth", "cli", "browser-flow"]
  }
]
```
"""


def extract(narrative: str) -> list[dict]:
    client = Anthropic()
    resp = client.messages.create(
        model=EXTRACTOR_MODEL,
        max_tokens=8000,
        system=EXTRACT_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"## Session transcript\n\n{narrative}\n\n"
                    "Now output the JSON array of events. Start with `[` and end with `]`."
                ),
            },
            {"role": "assistant", "content": "["},
        ],
    )
    text = "[" + "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    end = text.rfind("]")
    if end == -1:
        raise RuntimeError(f"Could not find closing `]` in extractor output:\n{text[:500]}")
    return json.loads(text[: end + 1])


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: extract_session.py SESSION.jsonl", file=sys.stderr)
        sys.exit(2)
    records = walk_jsonl(sys.argv[1])
    narrative = build_narrative(records)
    print(f"narrative: {len(narrative)} chars, {len(records)} records", file=sys.stderr)
    events = extract(narrative)
    print(f"extracted {len(events)} events", file=sys.stderr)
    json.dump(events, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
