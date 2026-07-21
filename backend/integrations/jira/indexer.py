"""Jira project → jira_documents indexer (index only; search federated to JQL).

A Jira source's external_ref is "{cloudId}:{projectKey}". We don't copy issue
bodies — Jira's own search (JQL `text ~`) is strong, so search is federated live
(see `search_jira`) and the body is fetched lazily on read (`fetch_jira_content`).
The sync only builds the navigable index: one row per issue, keyed by its key
with a zero-padded number ("PROJ-00123") so the project lists in issue order
(path order is the VFS listing order; bare "PROJ-123" would put PROJ-1000 before
PROJ-2). The display name keeps the real key; external_ref stores cloudId:key
for lazy fetch.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

API_BASE = "https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"


def _parse_time(value: str | None) -> datetime | None:
    """Jira returns ISO-8601 with a compact offset ('...+0000'); the column is
    timestamptz."""
    if not value:
        return None
    return datetime.fromisoformat(value)


ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
# cloud_id -> site base url (e.g. https://acme.atlassian.net). Cached because the
# site url never changes for a cloud and the lookup costs a network round-trip.
_SITE_URL_CACHE: dict[str, str] = {}
# Fields rendered for a full issue body (lazy reads and search hits). Keep this
# in sync with `_render_issue` — every field here should have a corresponding
# render branch, or the network round-trip is wasted.
ISSUE_FIELDS = ",".join(
    [
        # core
        "summary",
        "status",
        "priority",
        "issuetype",
        "assignee",
        "reporter",
        "created",
        "updated",
        "duedate",
        # body + activity
        "description",
        "comment",
        # taxonomy
        "labels",
        "components",
        "fixVersions",
        # graph (links + hierarchy)
        "issuelinks",
        "subtasks",
        "parent",
        # files
        "attachment",
    ]
)
PAGE_SIZE = 100
MAX_ISSUES = 2000
SEARCH_LIMIT = 25


def _jql_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _issue_path(key: str) -> str:
    """ "PROJ-123" → "PROJ-00123": zero-padded so the project lists numerically."""
    project, _, number = key.rpartition("-")
    return f"{project}-{int(number):05d}"


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


def _name(obj: dict | None) -> str:
    """Pull `.name` out of a nullable Jira reference (status, priority, etc)."""
    return (obj or {}).get("name") or ""


def _display_name(obj: dict | None) -> str:
    return (obj or {}).get("displayName") or ""


def _render_issue(issue: dict) -> str:
    fields = issue.get("fields", {})
    key = issue.get("key", "")
    summary = fields.get("summary") or ""

    # Header metadata block.
    meta_lines = [
        f"Status: {_name(fields.get('status'))}",
        f"Type: {_name(fields.get('issuetype'))}",
        f"Priority: {_name(fields.get('priority'))}",
        f"Assignee: {_display_name(fields.get('assignee')) or 'Unassigned'}",
        f"Reporter: {_display_name(fields.get('reporter')) or 'Unknown'}",
    ]
    for field, label in (("created", "Created"), ("updated", "Updated"), ("duedate", "Due")):
        value = fields.get(field)
        if value:
            meta_lines.append(f"{label}: {value}")

    labels = fields.get("labels") or []
    if labels:
        meta_lines.append("Labels: " + ", ".join(labels))
    components = [c.get("name", "") for c in (fields.get("components") or [])]
    if components:
        meta_lines.append("Components: " + ", ".join(components))
    fix_versions = [v.get("name", "") for v in (fields.get("fixVersions") or [])]
    if fix_versions:
        meta_lines.append("Fix versions: " + ", ".join(fix_versions))

    parent = fields.get("parent")
    if parent:
        parent_key = parent.get("key", "")
        parent_summary = (parent.get("fields") or {}).get("summary", "")
        meta_lines.append(f"Parent: {parent_key} {parent_summary}".rstrip())

    parts = [f"# {key}: {summary}", "\n".join(meta_lines)]

    description = _adf_to_text(fields.get("description"))
    if description:
        parts.append(f"\n{description}")

    # Issue links: "blocks", "is blocked by", "relates to", etc.
    link_lines: list[str] = []
    for link in fields.get("issuelinks") or []:
        link_type = link.get("type") or {}
        if "outwardIssue" in link:
            other = link["outwardIssue"]
            relation = link_type.get("outward") or "links to"
        elif "inwardIssue" in link:
            other = link["inwardIssue"]
            relation = link_type.get("inward") or "linked from"
        else:
            continue
        other_key = other.get("key", "")
        other_summary = (other.get("fields") or {}).get("summary", "")
        link_lines.append(f"- {relation} {other_key}: {other_summary}")
    if link_lines:
        parts.append("\n## Links\n" + "\n".join(link_lines))

    # Subtasks: key + summary + status.
    subtask_lines: list[str] = []
    for sub in fields.get("subtasks") or []:
        sub_key = sub.get("key", "")
        sub_fields = sub.get("fields") or {}
        sub_summary = sub_fields.get("summary", "")
        sub_status = _name(sub_fields.get("status"))
        subtask_lines.append(f"- {sub_key} ({sub_status}): {sub_summary}")
    if subtask_lines:
        parts.append("\n## Subtasks\n" + "\n".join(subtask_lines))

    # Attachments: filename + content URL (so the agent can fetch them).
    attach_lines: list[str] = []
    for att in fields.get("attachment") or []:
        filename = att.get("filename", "")
        url = att.get("content", "")
        attach_lines.append(f"- [{filename}]({url})" if url else f"- {filename}")
    if attach_lines:
        parts.append("\n## Attachments\n" + "\n".join(attach_lines))

    # Comments stay last — they tend to be the most verbose section.
    comments = (fields.get("comment") or {}).get("comments", []) or []
    rendered_comments = []
    for c in comments:
        author = _display_name(c.get("author")) or "Unknown"
        body = _adf_to_text(c.get("body"))
        if body:
            rendered_comments.append(f"{author}: {body}")
    if rendered_comments:
        parts.append("\n## Comments\n" + "\n\n".join(rendered_comments))

    return "\n".join(parts)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


async def index_jira(source: dict) -> str | None:
    """Build the navigable index only — one row per issue (key + title), no body.
    The body is fetched lazily on read and search is federated to JQL."""
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    cloud_id, project_key = source_service.parse_jira_project_ref(source["external_ref"])

    token = await get_valid_token(owner_user_id, "jira")
    base = API_BASE.format(cloud_id=cloud_id)
    jql = f'project = "{_jql_escape(project_key)}" ORDER BY updated DESC'

    present: list[str] = []
    next_page_token: str | None = None
    async with httpx.AsyncClient(timeout=60.0, headers=_headers(token)) as client:
        while len(present) < MAX_ISSUES:
            params = {"jql": jql, "maxResults": PAGE_SIZE, "fields": "summary,updated"}
            if next_page_token:
                params["nextPageToken"] = next_page_token
            resp = await client.get(f"{base}/search/jql", params=params)
            resp.raise_for_status()
            payload = resp.json()
            for issue in payload.get("issues", []):
                key = issue.get("key")
                if not key:
                    continue
                fields = issue.get("fields") or {}
                summary = fields.get("summary") or key
                path = _issue_path(key)
                await source_service.upsert_index_row(
                    table="jira_documents",
                    source_id=source_id,
                    owner_user_id=owner_user_id,
                    path=path,
                    name=f"{key}: {summary}",
                    kind="issue",
                    external_ref=f"{cloud_id}:{key}",
                    external_updated_at=_parse_time(fields.get("updated")),
                )
                present.append(path)
            if payload.get("isLast") or not payload.get("nextPageToken"):
                break
            next_page_token = payload["nextPageToken"]

    await source_service.remove_missing_documents("jira_documents", source_id, present)
    logger.info("jira source %s: indexed %d issue(s)", source_id, len(present))
    return None


async def search_jira(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Federated search: run JQL `text ~` against the project, live. Returns hits
    keyed by the index path so read_source resolves them. Requests the full
    ISSUE_FIELDS payload so each hit's snippet is the rendered issue body —
    same response count, callers get full text to rank on."""
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
            params={"jql": jql, "maxResults": min(limit, 50), "fields": ISSUE_FIELDS},
        )
        resp.raise_for_status()
        issues = resp.json().get("issues", [])
    hits = []
    for issue in issues:
        key = issue.get("key")
        if not key:
            continue
        summary = (issue.get("fields") or {}).get("summary") or ""
        hits.append(
            {
                "ref": _issue_path(key),
                "name": f"{key}: {summary}",
                "snippet": _render_issue(issue),
                "date_modified": _parse_time((issue.get("fields") or {}).get("updated")),
            }
        )
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
