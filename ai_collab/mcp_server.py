"""FastMCP stdio server exposing AI session history tools."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from . import git_utils
from .config import settings

mcp = FastMCP(
    "ai-collab",
    instructions=(
        "AI session history for this repository. Use these tools to see what "
        "other Claude Code agents have done recently, understand commit context, "
        "and avoid duplicating work."
    ),
)


def _repo_url() -> str:
    return git_utils.remote_url() or "unknown"


def _api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET from the Boozle API. Returns parsed JSON or None on error."""
    api_url = settings.API_URL
    api_key = settings.API_KEY
    if not api_url or not api_key:
        return None

    url = f"{api_url.rstrip('/')}{path}"
    if params:
        qs = "&".join(
            f"{k}={urllib.parse.quote(str(v))}"
            for k, v in params.items()
            if v is not None
        )
        if qs:
            url = f"{url}?{qs}"

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _fmt_session(s: dict) -> str:
    ended = s.get("ended_at") or "active"
    sha_start = (s.get("head_sha_start") or "?")[:8]
    sha_end = (s.get("head_sha_end") or "?")[:8]
    return (
        f"  [{s['id'][:8]}] {s['user_name']} on {s.get('branch', '?')}\n"
        f"    started: {s['started_at']}  ended: {ended}\n"
        f"    sha: {sha_start}..{sha_end}"
    )


def _fmt_event(e: dict) -> str:
    summary = e.get("summary") or "(no summary)"
    return f"  [{e['timestamp']}] {e['event_type']}: {summary}"


@mcp.tool()
def recent_activity(
    limit: int = 10,
    since_hours: Optional[int] = None,
    branch: Optional[str] = None,
) -> str:
    """Show recent AI sessions on this repository.

    Args:
        limit: Max number of sessions to return (default 10).
        since_hours: Only show sessions from the last N hours.
        branch: Filter to sessions on a specific branch.
    """
    params: dict[str, Any] = {"repo_url": _repo_url(), "limit": limit}
    if since_hours:
        params["since_hours"] = since_hours
    if branch:
        params["branch"] = branch

    sessions = _api_get("/api/v1/ai-collab/sessions", params)
    if not sessions:
        return "No recent AI sessions found for this repository."
    lines = [f"Recent AI sessions ({len(sessions)}):"]
    for s in sessions:
        lines.append(_fmt_session(s))
    return "\n".join(lines)


@mcp.tool()
def session_detail(session_id: str) -> str:
    """Get the full event log for a specific AI session.

    Args:
        session_id: The session ID (or first 8 chars).
    """
    session = _api_get(f"/api/v1/ai-collab/sessions/{session_id}")
    if not session:
        return f"Session '{session_id}' not found."

    events = _api_get(f"/api/v1/ai-collab/sessions/{session_id}/events") or []
    lines = [
        f"Session: {session['id']}",
        f"  user: {session['user_name']}",
        f"  branch: {session.get('branch', '?')}",
        f"  started: {session['started_at']}",
        f"  ended: {session.get('ended_at') or 'active'}",
        f"  sha range: {(session.get('head_sha_start') or '?')[:8]}..{(session.get('head_sha_end') or '?')[:8]}",
        f"\nEvents ({len(events)}):",
    ]
    for e in events:
        lines.append(_fmt_event(e))
    return "\n".join(lines)


@mcp.tool()
def commit_context(sha: str) -> str:
    """Find which AI session created a commit and why.

    Args:
        sha: The git commit SHA.
    """
    commit = _api_get(f"/api/v1/ai-collab/commits/{sha}")
    if not commit:
        return f"No AI session record found for commit {sha[:8]}."

    lines = [
        f"Commit: {commit['sha'][:8]}",
        f"  message: {commit.get('message', '?')}",
        f"  author: {commit.get('author', '?')}",
        f"  session: {commit['session_id']}",
        f"  session user: {commit.get('user_name', '?')}",
        f"  branch: {commit.get('branch', '?')}",
        f"  session time: {commit.get('session_started', '?')} — {commit.get('session_ended') or 'active'}",
    ]
    return "\n".join(lines)


@mcp.tool()
def search_activity(query: str, limit: int = 20) -> str:
    """Full-text search over AI session prompts and summaries.

    Args:
        query: Search query string.
        limit: Max number of results (default 20).
    """
    results = _api_get("/api/v1/ai-collab/search", {
        "q": query,
        "repo_url": _repo_url(),
        "limit": limit,
    })
    if not results:
        return f"No results found for '{query}'."

    lines = [f"Search results for '{query}' ({len(results)}):"]
    for r in results:
        lines.append(
            f"  [{r['timestamp']}] {r['event_type']} by {r.get('user_name', '?')} on {r.get('branch', '?')}\n"
            f"    {r.get('summary', '(no summary)')}"
        )
    return "\n".join(lines)


@mcp.tool()
def is_commit_current(sha: str) -> str:
    """Check whether a commit is an ancestor of the current HEAD.

    Args:
        sha: The git commit SHA to check.
    """
    current = git_utils.is_ancestor(sha)
    head = git_utils.head_sha()
    if current:
        return f"Commit {sha[:8]} IS an ancestor of current HEAD ({head[:8]}). The changes are included."
    else:
        return f"Commit {sha[:8]} is NOT an ancestor of current HEAD ({head[:8]}). The changes may have been reverted or are on another branch."


def run_server() -> None:
    """Start the MCP stdio server."""
    mcp.run(transport="stdio")
