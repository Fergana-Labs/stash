"""Linear GraphQL API client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from ..config import settings

ISSUE_QUERY = """
query Issue($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    description
    url
    updatedAt
    state { name }
    assignee { name }
    team { key name }
    project { name }
  }
}
"""

# Lists every issue the connected user can read, newest first, for the navigable
# index. Only the fields the index needs — the body is fetched lazily on read.
ISSUES_QUERY = """
query Issues($after: String) {
  issues(first: 100, after: $after, orderBy: updatedAt) {
    nodes { identifier title updatedAt }
    pageInfo { hasNextPage endCursor }
  }
}
"""

# Linear's native full-text search, used for federated source search. Selects
# the same fields as ISSUE_QUERY so each hit carries its full body — one
# request either way, and callers get full text to rank on.
SEARCH_QUERY = """
query SearchIssues($term: String!, $first: Int!) {
  searchIssues(term: $term, first: $first) {
    nodes {
      id
      identifier
      title
      description
      url
      updatedAt
      state { name }
      assignee { name }
      team { key name }
      project { name }
    }
  }
}
"""


@dataclass(frozen=True)
class LinearIssue:
    issue_id: str
    identifier: str
    title: str
    url: str
    status: str | None
    assignee_name: str | None
    team_key: str | None
    team_name: str | None
    project_name: str | None
    updated_at: datetime | None
    description: str | None = None


def is_configured() -> bool:
    return bool(settings.LINEAR_OAUTH_CLIENT_ID and settings.LINEAR_OAUTH_CLIENT_SECRET)


def _issue_from_node(issue: dict[str, Any]) -> LinearIssue:
    state = issue.get("state") or {}
    assignee = issue.get("assignee") or {}
    team = issue.get("team") or {}
    project = issue.get("project") or {}
    updated_at = issue.get("updatedAt")

    return LinearIssue(
        issue_id=issue["id"],
        identifier=issue["identifier"],
        title=issue["title"],
        url=issue["url"],
        status=state.get("name"),
        assignee_name=assignee.get("name"),
        team_key=team.get("key"),
        team_name=team.get("name"),
        project_name=project.get("name"),
        updated_at=_parse_datetime(updated_at) if updated_at else None,
        description=issue.get("description"),
    )


async def fetch_issue(ticket_identifier: str, access_token: str) -> LinearIssue | None:
    payload = await _graphql(ISSUE_QUERY, {"id": ticket_identifier}, access_token)
    _raise_on_errors(payload, "issue lookup")

    issue = payload.get("data", {}).get("issue")
    if not issue:
        return None
    return _issue_from_node(issue)


async def list_issues(
    access_token: str, after: str | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    """One page of issues the connected user can read, newest first. Returns the
    page's lightweight rows (identifier/title/updated_at) and the next cursor, or
    None when the listing is exhausted."""
    payload = await _graphql(ISSUES_QUERY, {"after": after}, access_token)
    _raise_on_errors(payload, "issue listing")

    connection = payload.get("data", {}).get("issues") or {}
    page_info = connection.get("pageInfo") or {}
    issues = [
        {
            "identifier": node["identifier"],
            "title": node.get("title") or node["identifier"],
            "updated_at": _parse_datetime(node["updatedAt"]) if node.get("updatedAt") else None,
        }
        for node in connection.get("nodes") or []
        if node.get("identifier")
    ]
    next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None
    return issues, next_cursor


async def search_issues(access_token: str, term: str, first: int = 25) -> list[LinearIssue]:
    """Linear's native full-text issue search. Returns full issues."""
    payload = await _graphql(SEARCH_QUERY, {"term": term, "first": first}, access_token)
    _raise_on_errors(payload, "issue search")

    nodes = (payload.get("data", {}).get("searchIssues") or {}).get("nodes") or []
    return [_issue_from_node(node) for node in nodes if node.get("identifier")]


def _raise_on_errors(payload: dict[str, Any], action: str) -> None:
    errors = payload.get("errors")
    if errors:
        message = "; ".join(str(error.get("message", error)) for error in errors)
        raise RuntimeError(f"Linear {action} failed: {message}")


async def _graphql(query: str, variables: dict[str, Any], access_token: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            settings.LINEAR_API_URL,
            headers=headers,
            json={"query": query, "variables": variables},
        )
    response.raise_for_status()
    return response.json()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
