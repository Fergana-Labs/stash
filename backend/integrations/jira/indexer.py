"""Jira project → jira_documents indexer (index only; search federated to JQL).

A Jira source's external_ref is "{cloudId}:{projectKey}". We don't copy issue
bodies — Jira's own search (JQL `text ~`) is strong, so search is federated live
(see `search_jira`) and the body is fetched lazily on read (`fetch_jira_content`).
The sync only builds the navigable index: one row per issue keyed by its key
(PROJ-123), storing the cloudId:key in external_ref for lazy fetch.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

API_BASE = "https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
# cloud_id -> site base url (e.g. https://acme.atlassian.net). Cached because the
# site url never changes for a cloud and the lookup costs a network round-trip.
_SITE_URL_CACHE: dict[str, str] = {}
# Fields rendered for a full read (lazy fetch).
ISSUE_FIELDS = "summary,status,assignee,updated,description,comment"
PAGE_SIZE = 100
MAX_ISSUES = 2000
SEARCH_LIMIT = 25


def _jql_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


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


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


async def index_jira(source: dict) -> str | None:
    """Build the navigable index only — one row per issue (key + title), no body.
    The body is fetched lazily on read and search is federated to JQL."""
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    cloud_id, project_key = source_service.parse_jira_project_ref(source["external_ref"])

    token = await get_valid_token(owner_user_id, "jira")
    base = API_BASE.format(cloud_id=cloud_id)
    jql = f'project = "{_jql_escape(project_key)}" ORDER BY updated DESC'

    present: list[str] = []
    next_page_token: str | None = None
    async with httpx.AsyncClient(timeout=60.0, headers=_headers(token)) as client:
        while len(present) < MAX_ISSUES:
            params = {"jql": jql, "maxResults": PAGE_SIZE, "fields": "summary"}
            if next_page_token:
                params["nextPageToken"] = next_page_token
            resp = await client.get(f"{base}/search/jql", params=params)
            resp.raise_for_status()
            payload = resp.json()
            for issue in payload.get("issues", []):
                key = issue.get("key")
                if not key:
                    continue
                summary = (issue.get("fields") or {}).get("summary") or key
                await source_service.upsert_index_row(
                    table="jira_documents",
                    source_id=source_id,
                    workspace_id=workspace_id,
                    path=key,
                    name=f"{key}: {summary}",
                    kind="issue",
                    external_ref=f"{cloud_id}:{key}",
                )
                present.append(key)
            if payload.get("isLast") or not payload.get("nextPageToken"):
                break
            next_page_token = payload["nextPageToken"]

    await source_service.soft_delete_missing("jira_documents", source_id, present)
    logger.info("jira source %s: indexed %d issue(s)", source_id, len(present))
    return None


async def search_jira(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Federated search: run JQL `text ~` against the project, live. Returns hits
    keyed by issue key (which is the index path, so read_source resolves them)."""
    owner_user_id = UUID(source["owner_user_id"])
    cloud_id, project_key = source_service.parse_jira_project_ref(source["external_ref"])
    token = await get_valid_token(owner_user_id, "jira")
    base = API_BASE.format(cloud_id=cloud_id)
    jql = (
        f'project = "{_jql_escape(project_key)}" '
        f'AND text ~ "{_jql_escape(query)}" ORDER BY updated DESC'
    )
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(
            f"{base}/search/jql",
            params={"jql": jql, "maxResults": min(limit, 50), "fields": "summary"},
        )
        resp.raise_for_status()
        issues = resp.json().get("issues", [])
    hits = []
    for issue in issues:
        key = issue.get("key")
        if not key:
            continue
        summary = (issue.get("fields") or {}).get("summary") or ""
        hits.append({"ref": key, "name": f"{key}: {summary}", "snippet": summary})
    return hits


async def site_url(source: dict) -> str | None:
    """The Jira site base url (e.g. https://acme.atlassian.net) for this source's
    cloud, used to build issue deep links. Resolves the cloud_id from external_ref
    ("{cloudId}:{projectKey}") against the owner's accessible Atlassian resources.
    Cached per cloud_id; returns None if the cloud isn't in the owner's resources."""
    cloud_id, _project_key = source_service.parse_jira_project_ref(source["external_ref"])
    if cloud_id in _SITE_URL_CACHE:
        return _SITE_URL_CACHE[cloud_id]

    token = await get_valid_token(UUID(source["owner_user_id"]), "jira")
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(ACCESSIBLE_RESOURCES_URL)
        resp.raise_for_status()
        resources = resp.json()
    for resource in resources:
        if resource.get("id") == cloud_id and resource.get("url"):
            _SITE_URL_CACHE[cloud_id] = resource["url"]
            return resource["url"]
    return None


async def fetch_jira_content(owner_user_id: UUID, external_ref: str) -> str:
    """Lazy read: render a single issue. `external_ref` is "{cloudId}:{key}"."""
    cloud_id, _, key = external_ref.partition(":")
    token = await get_valid_token(owner_user_id, "jira")
    base = API_BASE.format(cloud_id=cloud_id)
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(f"{base}/issue/{key}", params={"fields": ISSUE_FIELDS})
        resp.raise_for_status()
        return _render_issue(resp.json())
