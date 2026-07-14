"""Linear issues → linear_index indexer (index only; search federated).

A Linear source covers every issue the connected user can read. We don't copy
issue bodies — Linear's own search is used live (see `search_linear`) and the
description is fetched lazily on read (`fetch_linear_content`). The sync only
builds the navigable index: one row per issue, filed under its team with a
zero-padded number ("FER/FER-00199") so each team folder lists in issue order
(path order is the VFS listing order; bare "FER-199" would put FER-1000 before
FER-2). The display name keeps the real identifier.
"""

from __future__ import annotations

import logging
from uuid import UUID

from ...services import linear_api_service, source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

MAX_ISSUES = 5000
SEARCH_LIMIT = 25


def _issue_path(identifier: str) -> str:
    """ "FER-199" → "FER/FER-00199": one folder per team, numerically ordered."""
    team_key, _, number = identifier.rpartition("-")
    return f"{team_key}/{team_key}-{int(number):05d}"


def _render_issue(issue: linear_api_service.LinearIssue) -> str:
    parts = [
        f"# {issue.identifier} {issue.title}",
        f"Status: {issue.status or '—'}",
        f"Assignee: {issue.assignee_name or 'Unassigned'}",
    ]
    if issue.team_key or issue.team_name:
        parts.append(f"Team: {issue.team_name or issue.team_key}")
    if issue.project_name:
        parts.append(f"Project: {issue.project_name}")
    parts.append(f"URL: {issue.url}")
    if (issue.description or "").strip():
        parts.append(f"\n{issue.description.strip()}")
    return "\n".join(parts)


async def index_linear(source: dict) -> str | None:
    """Build the navigable index only — one row per issue (identifier + title)."""
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])

    token = await get_valid_token(owner_user_id, "linear")

    present: list[str] = []
    cursor: str | None = None
    while len(present) < MAX_ISSUES:
        issues, cursor = await linear_api_service.list_issues(token, cursor)
        for issue in issues:
            identifier = issue["identifier"]
            path = _issue_path(identifier)
            await source_service.upsert_index_row(
                table="linear_index",
                source_id=source_id,
                owner_user_id=owner_user_id,
                path=path,
                name=f"{identifier} {issue['title']}",
                kind="issue",
                external_ref=identifier,
                external_updated_at=issue["updated_at"],
            )
            present.append(path)
        if not cursor:
            break

    await source_service.remove_missing_documents("linear_index", source_id, present)
    logger.info("linear source %s: indexed %d issue(s)", source_id, len(present))
    return None


async def search_linear(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Federated search via Linear's native issue search. Returns hits keyed by
    the index path so read_source resolves them. Each hit's snippet is the
    rendered issue body — the search response already carries it, so callers
    get full text to rank on at no extra request cost."""
    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "linear")
    issues = await linear_api_service.search_issues(token, query, min(limit, 50))
    return [
        {
            "ref": _issue_path(issue.identifier),
            "name": f"{issue.identifier} {issue.title}",
            "snippet": _render_issue(issue),
        }
        for issue in issues
    ]


async def fetch_linear_content(owner_user_id: UUID, identifier: str) -> str:
    """Lazy read: render a single issue. `external_ref` is the issue identifier."""
    token = await get_valid_token(owner_user_id, "linear")
    issue = await linear_api_service.fetch_issue(identifier, token)
    if issue is None:
        return ""
    return _render_issue(issue)
