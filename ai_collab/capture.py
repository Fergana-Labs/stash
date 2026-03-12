"""Hook event processing: reads Claude Code hook JSON from stdin, writes to DB."""

from __future__ import annotations

import json
import sys
from typing import Any

from . import db, git_utils

MAX_PAYLOAD_CHARS = 2000
MAX_SUMMARY_CHARS = 200


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit - 3] + "..."


def _sanitize_data(data: dict[str, Any]) -> dict[str, Any]:
    """Truncate large string values in hook data."""
    sanitized = {}
    for k, v in data.items():
        if isinstance(v, str) and len(v) > MAX_PAYLOAD_CHARS:
            sanitized[k] = _truncate(v, MAX_PAYLOAD_CHARS)
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_data(v)
        elif isinstance(v, list):
            sanitized[k] = [
                _sanitize_data(item) if isinstance(item, dict)
                else _truncate(item, MAX_PAYLOAD_CHARS) if isinstance(item, str) and len(item) > MAX_PAYLOAD_CHARS
                else item
                for item in v
            ]
        else:
            sanitized[k] = v
    return sanitized


def _extract_summary(event_type: str, data: dict[str, Any]) -> str | None:
    """Extract a human-readable summary based on event type."""
    if event_type == "UserPromptSubmit":
        prompt = data.get("prompt", "")
        if isinstance(prompt, str):
            return _truncate(prompt, MAX_SUMMARY_CHARS)

    if event_type == "Stop":
        # Try to get last assistant message
        stop_reason = data.get("stop_reason", "")
        summary_parts = []
        if stop_reason:
            summary_parts.append(f"stop: {stop_reason}")
        message = data.get("message", "")
        if isinstance(message, str) and message:
            summary_parts.append(_truncate(message, MAX_SUMMARY_CHARS))
        return " — ".join(summary_parts) if summary_parts else None

    if event_type == "PostToolUse":
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})
        if tool_name == "Bash":
            cmd = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
            return _truncate(f"bash: {cmd}", MAX_SUMMARY_CHARS)
        if tool_name in ("Write", "Edit"):
            path = tool_input.get("file_path", "") if isinstance(tool_input, dict) else ""
            return _truncate(f"{tool_name.lower()}: {path}", MAX_SUMMARY_CHARS)
        return _truncate(f"tool: {tool_name}", MAX_SUMMARY_CHARS)

    return None


def _detect_git_commit(event_type: str, data: dict[str, Any]) -> str | None:
    """If this is a PostToolUse Bash event with a git commit, return the new SHA."""
    if event_type != "PostToolUse":
        return None
    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        return None
    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str):
        return None
    # Check if command contains a git commit
    if "git commit" in command or "git merge" in command:
        # Get the current HEAD which should be the new commit
        return git_utils.head_sha()
    return None


def process_hook_event(raw: str) -> None:
    """Process a single hook event from stdin JSON."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    session_id = data.get("session_id", "")
    if not session_id:
        return

    event_type = data.get("type", data.get("event", ""))
    if not event_type:
        return

    sha = git_utils.head_sha() or "unknown"
    repo_url = git_utils.remote_url() or "unknown"
    current_branch = git_utils.branch()
    cwd = data.get("cwd", "")

    # Handle SessionStart: create/update session row
    if event_type == "SessionStart":
        db.upsert_session(
            session_id=session_id,
            repo_url=repo_url,
            user_name=git_utils.user_name(),
            branch=current_branch,
            head_sha=sha,
            cwd=cwd,
        )
        return

    # Handle Stop: also end the session
    if event_type == "Stop":
        db.end_session(session_id, head_sha=sha)

    # Sanitize and store event
    sanitized = _sanitize_data(data)
    summary = _extract_summary(event_type, data)

    db.insert_event(
        session_id=session_id,
        event_type=event_type,
        head_sha=sha,
        data=sanitized,
        summary=summary,
    )

    # Check for git commit in PostToolUse Bash events
    commit_sha = _detect_git_commit(event_type, data)
    if commit_sha and commit_sha != "unknown":
        tool_input = data.get("tool_input", {})
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        db.insert_commit(
            sha=commit_sha,
            session_id=session_id,
            repo_url=repo_url,
            message=_truncate(command, MAX_SUMMARY_CHARS),
            author=git_utils.user_name(),
        )


def record_from_stdin() -> None:
    """Read hook JSON from stdin and process it."""
    raw = sys.stdin.read()
    if raw.strip():
        process_hook_event(raw)
