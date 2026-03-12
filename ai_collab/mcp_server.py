"""FastMCP stdio server exposing AI session history tools."""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import db, git_utils

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


def _fmt_session(s: dict) -> str:
    ended = s.get("ended_at") or "active"
    return (
        f"  [{s['id'][:8]}] {s['user_name']} on {s.get('branch', '?')}\n"
        f"    started: {s['started_at']}  ended: {ended}\n"
        f"    sha: {s.get('head_sha_start', '?')[:8]}..{(s.get('head_sha_end') or '?')[:8]}"
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
    sessions = db.recent_sessions(
        repo_url=_repo_url(),
        limit=limit,
        since_hours=since_hours,
        branch=branch,
    )
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
    # Try exact match first, then prefix match
    session = db.session_by_id(session_id)
    if not session:
        # Try prefix match via recent sessions
        sessions = db.recent_sessions(repo_url=_repo_url(), limit=100)
        for s in sessions:
            if s["id"].startswith(session_id):
                session = db.session_by_id(s["id"])
                session_id = s["id"]
                break

    if not session:
        return f"Session '{session_id}' not found."

    events = db.session_events(session_id)
    lines = [
        f"Session: {session['id']}",
        f"  user: {session['user_name']}",
        f"  branch: {session.get('branch', '?')}",
        f"  started: {session['started_at']}",
        f"  ended: {session.get('ended_at') or 'active'}",
        f"  sha range: {session.get('head_sha_start', '?')[:8]}..{(session.get('head_sha_end') or '?')[:8]}",
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
    commit = db.commit_by_sha(sha)
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
    results = db.search_events(
        repo_url=_repo_url(),
        query=query,
        limit=limit,
    )
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
