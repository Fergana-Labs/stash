"""Asana project → asana_documents indexer (index only; search federated).

An Asana source's external_ref is a project gid. We don't copy task bodies —
Asana's own search (`/tasks/search`, paid tiers) is used live (see `search_asana`)
and the body is fetched lazily on read (`fetch_asana_content`). The sync only
builds the navigable index: one row per task, filed under its section in this
project ("Section/Task name (gid)") so the project reads like its board instead
of a flat pile of opaque gids (path order is the VFS listing order).
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

API_BASE = "https://app.asana.com/api/1.0"
TASKS_URL = API_BASE + "/projects/{project_gid}/tasks"
# Fields rendered for a full task body (lazy reads and search hits), plus
# modified_at, which search hits surface as date_modified.
TASK_FIELDS = "name,notes,completed,assignee.name,due_on,permalink_url,modified_at"
PAGE_SIZE = 100
MAX_TASKS = 2000
SEARCH_LIMIT = 25


def _parse_time(value: str | None) -> datetime | None:
    """Asana returns ISO-8601 ('...Z'); the column is timestamptz."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _render_task(task: dict) -> str:
    name = task.get("name") or "(untitled task)"
    status = "Completed" if task.get("completed") else "Open"
    assignee = (task.get("assignee") or {}).get("name") or "Unassigned"
    due = task.get("due_on") or "—"
    notes = task.get("notes") or ""
    parts = [
        f"# {name}",
        f"Status: {status}",
        f"Assignee: {assignee}",
        f"Due: {due}",
    ]
    if notes.strip():
        parts.append(f"\n{notes.strip()}")
    return "\n".join(parts)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _path_segment(text: str, max_len: int = 60) -> str:
    """A string safe to embed in an index path: no slashes (they'd read as
    folders), whitespace collapsed, capped so paths stay listable."""
    cleaned = " ".join(text.replace("/", "-").split())
    return cleaned[:max_len].strip()


def _task_section(task: dict, project_gid: str) -> str:
    """The task's section name within this project. Asana files every task in a
    project into a section; a payload without one lands in "(no section)" so the
    gap is visible instead of breaking the tree."""
    for membership in task.get("memberships") or []:
        if (membership.get("project") or {}).get("gid") != project_gid:
            continue
        name = (membership.get("section") or {}).get("name")
        if name:
            return name
    return "(no section)"


def _task_path(task: dict, project_gid: str) -> str:
    """Index path for a task: "Section/Task name (gid)". The section folder
    mirrors the project's board columns; the name leaf lists alphabetically and
    the gid suffix guarantees uniqueness."""
    section = _path_segment(_task_section(task, project_gid))
    name = _path_segment(task.get("name") or "(untitled task)")
    return f"{section}/{name} ({task['gid']})"


async def index_asana(source: dict) -> str | None:
    """Build the navigable index only — one row per task (gid + name), no body."""
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    project_gid = source["external_ref"]

    token = await get_valid_token(owner_user_id, "asana")
    url = TASKS_URL.format(project_gid=project_gid)

    present: list[str] = []
    offset: str | None = None
    async with httpx.AsyncClient(timeout=60.0, headers=_headers(token)) as client:
        while len(present) < MAX_TASKS:
            params = {
                "opt_fields": "name,modified_at,memberships.project.gid,memberships.section.name",
                "limit": PAGE_SIZE,
            }
            if offset:
                params["offset"] = offset
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
            for task in payload.get("data", []):
                gid = task.get("gid")
                if not gid:
                    continue
                path = _task_path(task, project_gid)
                await source_service.upsert_index_row(
                    table="asana_documents",
                    source_id=source_id,
                    owner_user_id=owner_user_id,
                    path=path,
                    name=task.get("name") or "(untitled task)",
                    kind="task",
                    external_ref=gid,
                    external_updated_at=_parse_time(task.get("modified_at")),
                )
                present.append(path)
            next_page = payload.get("next_page")
            if not next_page or not next_page.get("offset"):
                break
            offset = next_page["offset"]

    await source_service.remove_missing_documents("asana_documents", source_id, present)
    logger.info("asana source %s: indexed %d task(s)", source_id, len(present))
    return None


async def search_asana(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Federated search via Asana's `/tasks/search` (paid tiers only). Scoped to
    the project; maps the returned gids back to our index paths (so read_source
    resolves them) and only returns tasks we've indexed for this source.
    Requests the full TASK_FIELDS payload so each hit's snippet is the rendered
    task body — same request count, callers get full text to rank on."""
    owner_user_id = UUID(source["owner_user_id"])
    project_gid = source["external_ref"]
    token = await get_valid_token(owner_user_id, "asana")
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        # The search endpoint is workspace-scoped; resolve the project's workspace.
        proj = await client.get(
            f"{API_BASE}/projects/{project_gid}", params={"opt_fields": "workspace"}
        )
        proj.raise_for_status()
        workspace_gid = proj.json()["data"]["workspace"]["gid"]
        resp = await client.get(
            f"{API_BASE}/workspaces/{workspace_gid}/tasks/search",
            params={
                "text": query,
                "projects.any": project_gid,
                "opt_fields": TASK_FIELDS,
                "limit": min(limit, 100),
            },
        )
        resp.raise_for_status()
        tasks = resp.json().get("data", [])

    gids = [t["gid"] for t in tasks if t.get("gid")]
    paths = await source_service.index_paths_for_refs("asana_documents", UUID(source["id"]), gids)
    hits = []
    for task in tasks:
        entry = paths.get(task.get("gid"))
        if not entry:
            continue
        path, name = entry
        hits.append(
            {
                "ref": path,
                "name": name,
                "snippet": _render_task(task),
                "date_modified": _parse_time(task.get("modified_at")),
            }
        )
    return hits


async def fetch_asana_content(owner_user_id: UUID, gid: str) -> str:
    """Lazy read: render a single task. `external_ref` is the task gid."""
    token = await get_valid_token(owner_user_id, "asana")
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(f"{API_BASE}/tasks/{gid}", params={"opt_fields": TASK_FIELDS})
        resp.raise_for_status()
        return _render_task(resp.json().get("data", {}))
