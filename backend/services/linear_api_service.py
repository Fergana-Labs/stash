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
    url
    updatedAt
    state { name }
    assignee { name }
    team { key name }
    project { name }
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


def is_configured() -> bool:
    return bool(settings.LINEAR_OAUTH_CLIENT_ID and settings.LINEAR_OAUTH_CLIENT_SECRET)


async def fetch_issue(ticket_identifier: str, access_token: str) -> LinearIssue | None:
    payload = await _graphql(ISSUE_QUERY, {"id": ticket_identifier}, access_token)
    errors = payload.get("errors")
    if errors:
        message = "; ".join(str(error.get("message", error)) for error in errors)
        raise RuntimeError(f"Linear issue lookup failed: {message}")

    issue = payload.get("data", {}).get("issue")
    if not issue:
        return None

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
    )


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
