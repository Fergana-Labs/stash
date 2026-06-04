"""Jira project → jira_documents indexer (copied content; FTS-searchable).

A Jira source's external_ref is "{cloudId}:{projectKey}". We page through the
project's issues newest-first and copy each one into jira_documents as a text
document keyed by its issue key (e.g. PROJ-123), so the agent can search and
read them like any other source. Idempotent re-sync via source_service
(content-hash dedupe + soft-delete of issues that vanished).
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

API_BASE = "https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
# The enhanced JQL search endpoint (token-paginated). Requires explicit fields.
ISSUE_FIELDS = "summary,status,assignee,updated,description,comment"
PAGE_SIZE = 100
MAX_ISSUES = 2000


def _adf_to_text(node: dict | None) -> str:
    """Flatten an Atlassian Document Format node tree to plain text. We only
    care about the readable text — text nodes plus a newline after each block."""
    if not node:
        return ""
    out: list[str] = []

    def walk(n: dict) -> None:
        if n.get("type") == "text":
            out.append(n.get("text", ""))
        for child in n.get("content", []) or []:
            walk(child)
        # Block-level nodes end with a newline so paragraphs don't run together.
        if n.get("type") in ("paragraph", "heading", "listItem", "blockquote"):
            out.append("\n")

    walk(node)
    return "".join(out).strip()


def _render_issue(issue: dict) -> str:
    fields = issue.get("fields", {})
    key = issue.get("key", "")
    summary = fields.get("summary") or ""
    status = (fields.get("status") or {}).get("name") or ""
    assignee = (fields.get("assignee") or {}).get("displayName") or "Unassigned"
    description = _adf_to_text(fields.get("description"))

    comments = (fields.get("comment") or {}).get("comments", []) or []
    rendered_comments = []
    for c in comments:
        author = (c.get("author") or {}).get("displayName") or "Unknown"
        body = _adf_to_text(c.get("body"))
        if body:
            rendered_comments.append(f"{author}: {body}")

    parts = [
        f"# {key}: {summary}",
        f"Status: {status}",
        f"Assignee: {assignee}",
    ]
    if description:
        parts.append(f"\n{description}")
    if rendered_comments:
        parts.append("\n## Comments\n" + "\n\n".join(rendered_comments))
    return "\n".join(parts)


async def index_jira(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    cloud_id, _, project_key = source["external_ref"].partition(":")

    token = await get_valid_token(owner_user_id, "jira")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base = API_BASE.format(cloud_id=cloud_id)
    jql = f"project = {project_key} ORDER BY updated DESC"

    present: list[str] = []
    next_page_token: str | None = None
    async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
        while len(present) < MAX_ISSUES:
            params = {"jql": jql, "maxResults": PAGE_SIZE, "fields": ISSUE_FIELDS}
            if next_page_token:
                params["nextPageToken"] = next_page_token
            resp = await client.get(f"{base}/search/jql", params=params)
            resp.raise_for_status()
            payload = resp.json()
            for issue in payload.get("issues", []):
                key = issue.get("key")
                if not key:
                    continue
                await source_service.upsert_content_document(
                    table="jira_documents",
                    source_id=source_id,
                    workspace_id=workspace_id,
                    path=key,
                    name=key,
                    kind="issue",
                    content=_render_issue(issue),
                    external_ref=key,
                )
                present.append(key)
            if payload.get("isLast") or not payload.get("nextPageToken"):
                break
            next_page_token = payload["nextPageToken"]

    await source_service.soft_delete_missing("jira_documents", source_id, present)
    logger.info("jira source %s: indexed %d issue(s)", project_key, len(present))
    return None
