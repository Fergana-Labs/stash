"""Synchronous httpx client wrapping the Stash REST API."""

from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path

import httpx


class StashError(Exception):
    def __init__(self, status_code: int, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


# Page size when the VFS walks a source's entries. Callers page with the
# `after` cursor until a page comes back non-full.
SOURCE_ENTRIES_PAGE = 1000


class StashClient:
    def __init__(self, base_url: str, api_key: str = ""):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = httpx.Client(base_url=self._base_url, timeout=30)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = self._http.request(method, path, headers=headers, **kwargs)
        if not resp.is_success:
            detail = ""
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise StashError(resp.status_code, detail)
        return resp

    # The URL argument is named `url`, not `path`, so callers can pass a query
    # param literally named "path" (the source VFS does) without a kwarg clash.
    def _get(self, url: str, **params) -> dict | list:
        return self._request("GET", url, params=params).json()

    def _post(self, path: str, json=None) -> dict:
        resp = self._request("POST", path, json=json)
        return {} if resp.status_code == 204 else resp.json()

    def _put(self, path: str, json=None) -> dict:
        return self._request("PUT", path, json=json).json()

    def _patch(self, path: str, json=None) -> dict:
        return self._request("PATCH", path, json=json).json()

    def _delete(self, path: str) -> None:
        self._request("DELETE", path)

    def _list(self, url: str, key: str, **params) -> list:
        data = self._get(url, **params)
        return data.get(key, data) if isinstance(data, dict) else data

    def _upload(self, path: str, file_path: str, folder_id: str | None = None) -> dict:
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = {"folder_id": folder_id} if folder_id else None
        with open(file_path, "rb") as f:
            resp = self._request(
                "POST",
                path,
                files={"file": (filename, f, content_type)},
                data=data or None,
                timeout=300,
            )
        return resp.json()

    # --- Auth ---

    def register(self, name: str, description: str = "", password: str | None = None) -> dict:
        body: dict = {"name": name, "description": description}
        if password:
            body["password"] = password
        return self._post("/api/v1/users/register", json=body)

    def login(self, name: str, password: str) -> dict:
        return self._post("/api/v1/users/login", json={"name": name, "password": password})

    def whoami(self) -> dict:
        return self._get("/api/v1/users/me")

    def list_api_keys(self) -> list:
        return self._get("/api/v1/users/me/keys")

    def create_api_key(self, name: str, access: str) -> dict:
        return self._post("/api/v1/users/me/keys", json={"name": name, "access": access})

    def revoke_api_key(self, key_id: str) -> None:
        self._delete(f"/api/v1/users/me/keys/{key_id}")

    # --- Discover (public catalog, no auth required) ---

    def list_discover_skills(
        self,
        query: str = "",
        sort: str = "trending",
    ) -> dict:
        params: dict = {"sort": sort}
        if query:
            params["q"] = query
        return self._get("/api/v1/discover/skills", **params)

    # --- Skills (publishable subsets) ---

    def list_skills(self) -> list:
        return self._list("/api/v1/me/skills", "skills")

    def publish_skill_folder(
        self,
        folder_id: str,
        title: str | None = None,
        description: str = "",
        discoverable: bool = False,
    ) -> dict:
        body = {
            "folder_id": folder_id,
            "description": description,
            "discoverable": discoverable,
        }
        if title:
            body["title"] = title
        return self._post("/api/v1/me/skills", json=body)

    def update_skill(self, skill_id: str, **fields) -> dict:
        return self._patch(f"/api/v1/skills/{skill_id}", json=fields)

    def unpublish_skill(self, skill_id: str) -> None:
        self._delete(f"/api/v1/skills/{skill_id}")

    def fork_skill(self, slug: str) -> dict:
        return self._post(f"/api/v1/skills/{slug}/add-to-stash")

    def get_public_skill(self, slug: str) -> dict:
        return self._get(f"/api/v1/skills/{slug}")

    def get_skill_contents(self, folder_id: str) -> dict:
        return self._get(f"/api/v1/me/skills/{folder_id}/contents")

    def replace_skill_contents(self, folder_id: str, files: list[tuple[str, bytes]]) -> dict:
        """files is (path relative to the skill folder, bytes) pairs; the
        server replaces the folder's whole subtree with this set."""
        parts = [
            ("files", (path, blob, mimetypes.guess_type(path)[0] or "application/octet-stream"))
            for path, blob in files
        ]
        resp = self._request(
            "PUT",
            f"/api/v1/me/skills/{folder_id}/contents",
            files=parts,
            timeout=300,
        )
        return resp.json()

    def get_skill_text(self, slug: str) -> str:
        resp = self._request("GET", f"/api/v1/skills/{slug}", params={"format": "text"})
        return resp.text

    def snapshot_source_into_skill(self, skill_id: str, source_id: str, path: str) -> dict:
        return self._post(
            f"/api/v1/me/skills/{skill_id}/snapshot-source",
            json={"source_id": source_id, "path": path},
        )

    # --- Object sharing (grant a person access to a folder/file/session by email) ---

    def share_object(
        self,
        object_type: str,
        object_id: str,
        email: str,
        permission: str = "read",
        expires_at: str | None = None,
    ) -> dict:
        body = {
            "object_type": object_type,
            "object_id": object_id,
            "email": email,
            "permission": permission,
        }
        if expires_at:
            body["expires_at"] = expires_at
        return self._post("/api/v1/share", json=body)

    def unshare_object(
        self, object_type: str, object_id: str, principal_type: str, principal_id: str
    ) -> None:
        self._request(
            "DELETE",
            "/api/v1/share",
            json={
                "object_type": object_type,
                "object_id": object_id,
                "principal_type": principal_type,
                "principal_id": principal_id,
            },
        )

    def list_object_shares(self, object_type: str, object_id: str) -> list:
        return self._list("/api/v1/share", "shares", object_type=object_type, object_id=object_id)

    # --- Session folders (shareable grouping for sessions) ---

    def list_session_folders(self) -> list:
        return self._list("/api/v1/me/session-folders", "folders")

    def create_session_folder(self, name: str) -> dict:
        return self._post("/api/v1/me/session-folders", json={"name": name})

    def assign_session_folder(self, session_row_id: str, folder_id: str | None = None) -> dict:
        return self._post(
            "/api/v1/me/session-folders/assign",
            json={"session_row_id": session_row_id, "folder_id": folder_id},
        )

    # --- Aggregate ---

    def all_pages(self) -> list:
        return self._list("/api/v1/me/pages", "pages")

    # --- Folders (user-scoped, nestable) ---

    def list_folders(self) -> list:
        return self._list("/api/v1/me/folders", "folders")

    def create_folder(self, name: str, parent_folder_id: str | None = None) -> dict:
        body: dict = {"name": name}
        if parent_folder_id:
            body["parent_folder_id"] = parent_folder_id
        return self._post("/api/v1/me/folders", json=body)

    def delete_folder(self, folder_id: str) -> None:
        self._delete(f"/api/v1/me/folders/{folder_id}")

    def copy_folder(self, folder_id: str, target_folder_id: str | None = None) -> dict:
        body = {"target_folder_id": target_folder_id} if target_folder_id else {}
        return self._post(f"/api/v1/me/folders/{folder_id}/copy", json=body)

    def update_folder(
        self,
        folder_id: str,
        *,
        name: str | None = None,
        parent_folder_id: str | None = None,
        move_to_root: bool = False,
    ) -> dict:
        body: dict = {}
        if name is not None:
            body["name"] = name
        if move_to_root:
            body["move_to_root"] = True
        elif parent_folder_id is not None:
            body["parent_folder_id"] = parent_folder_id
        return self._patch(f"/api/v1/me/folders/{folder_id}", json=body)

    def get_tree(self) -> dict:
        return self._get("/api/v1/me/tree")

    def get_overview(self) -> dict:
        return self._get("/api/v1/me/overview")

    def get_memory_folder(self) -> dict:
        return self._get("/api/v1/me/memory-folder")

    def get_changes(self, since: str | None = None) -> dict:
        params = {"since": since} if since else {}
        return self._get("/api/v1/me/changes", **params)

    # --- Pages (user-scoped) ---

    def create_page(
        self,
        name: str,
        content: str = "",
        folder_id: str | None = None,
        content_type: str = "markdown",
        content_html: str = "",
        html_layout: str | None = None,
    ) -> dict:
        body: dict = {
            "name": name,
            "content": content,
            "content_type": content_type,
            "content_html": content_html,
        }
        if folder_id:
            body["folder_id"] = folder_id
        if html_layout:
            body["html_layout"] = html_layout
        return self._post("/api/v1/me/pages/new", json=body)

    def list_pages(self) -> list:
        return self._list("/api/v1/me/pages", "pages")

    def get_page(self, page_id: str) -> dict:
        return self._get(f"/api/v1/pages/{page_id}")

    def update_page(self, page_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/me/pages/{page_id}", json=kwargs)

    def delete_page(self, page_id: str) -> None:
        self._delete(f"/api/v1/me/pages/{page_id}")

    def restore_page(self, page_id: str) -> None:
        self._post(f"/api/v1/me/pages/{page_id}/restore")

    def purge_page(self, page_id: str) -> None:
        self._delete(f"/api/v1/me/pages/{page_id}/purge")

    def copy_page(self, page_id: str, target_folder_id: str | None = None) -> dict:
        body = {"target_folder_id": target_folder_id} if target_folder_id else {}
        return self._post(f"/api/v1/me/pages/{page_id}/copy", json=body)

    # --- Session events ---

    def list_agent_names(self) -> list:
        data = self._get("/api/v1/me/sessions/agent-names")
        return data.get("agent_names", []) if isinstance(data, dict) else data

    def push_event(
        self,
        agent_name: str,
        event_type: str,
        content: str,
        session_id: str,
        tool_name: str | None = None,
        metadata: dict | None = None,
        attachments: list[dict] | None = None,
        created_at: str | None = None,
    ) -> dict:
        body: dict = {
            "agent_name": agent_name,
            "event_type": event_type,
            "content": content,
            "session_id": session_id,
        }
        if tool_name:
            body["tool_name"] = tool_name
        if metadata:
            body["metadata"] = metadata
        if attachments:
            body["attachments"] = attachments
        if created_at:
            body["created_at"] = created_at
        return self._post("/api/v1/me/sessions/events", json=body)

    def query_events(
        self,
        agent_name: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        after: str | None = None,
        before: str | None = None,
        order: str = "desc",
    ) -> list:
        params: dict = {"limit": limit, "order": order}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        return self._list("/api/v1/me/sessions/events", "events", **params)

    def all_events(
        self,
        agent_name: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        after: str | None = None,
        before: str | None = None,
        order: str = "desc",
    ) -> list:
        params: dict = {"limit": limit, "order": order}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        return self._list("/api/v1/me/session-events", "events", **params)

    def push_events_batch(self, events: list[dict]) -> list:
        body: dict = {"events": events}
        return self._post("/api/v1/me/sessions/events/batch", json=body)

    def upload_transcript(
        self,
        session_id: str,
        transcript_path: str | Path,
        agent_name: str,
        cwd: str = "",
        replace: bool = False,
    ) -> dict:
        import gzip as _gzip

        with open(transcript_path, "rb") as f:
            raw = f.read()
        body = _gzip.compress(raw)
        name = os.path.basename(transcript_path)
        if not name.endswith(".gz"):
            name += ".gz"
        # History imports send thousands of sequential uploads, so transient
        # network blips are expected; retry a couple times before giving up.
        # Resending is safe: the server skips sessions that already exist.
        for attempt in range(3):
            try:
                resp = self._request(
                    "POST",
                    "/api/v1/me/transcripts",
                    data={
                        "session_id": session_id,
                        "agent_name": agent_name,
                        "cwd": cwd,
                        "replace": str(replace).lower(),
                    },
                    files={"file": (name, body, "application/gzip")},
                    timeout=120,
                )
                return resp.json()
            except httpx.TransportError:
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)

    # --- Files ---

    def upload_file(self, file_path: str, folder_id: str | None = None) -> dict:
        return self._upload("/api/v1/me/files", file_path, folder_id)

    def list_files(self) -> list:
        return self._list("/api/v1/me/files", "files")

    def get_file(self, file_id: str) -> dict:
        return self._get(f"/api/v1/me/files/{file_id}")

    def delete_file(self, file_id: str) -> None:
        self._delete(f"/api/v1/me/files/{file_id}")

    def copy_file(self, file_id: str, target_folder_id: str | None = None) -> dict:
        body = {"target_folder_id": target_folder_id} if target_folder_id else {}
        return self._post(f"/api/v1/me/files/{file_id}/copy", json=body)

    # --- Batch ops (best-effort move/delete/restore over many items) ---

    def batch_move(
        self,
        items: list[dict],
        target_folder_id: str | None = None,
        move_to_root: bool = False,
    ) -> dict:
        body: dict = {"items": items, "move_to_root": move_to_root}
        if target_folder_id:
            body["target_folder_id"] = target_folder_id
        return self._post("/api/v1/me/batch/move", json=body)

    def batch_delete(self, items: list[dict]) -> dict:
        return self._post("/api/v1/me/batch/delete", json={"items": items})

    def batch_restore(self, items: list[dict]) -> dict:
        return self._post("/api/v1/me/batch/restore", json={"items": items})

    def restore_file(self, file_id: str) -> None:
        self._post(f"/api/v1/me/files/{file_id}/restore")

    def purge_file(self, file_id: str) -> None:
        self._delete(f"/api/v1/me/files/{file_id}/purge")

    def update_file(
        self,
        file_id: str,
        *,
        name: str | None = None,
        folder_id: str | None = None,
        move_to_root: bool = False,
    ) -> dict:
        body: dict = {}
        if name is not None:
            body["name"] = name
        if move_to_root:
            body["move_to_root"] = True
        elif folder_id is not None:
            body["folder_id"] = folder_id
        return self._patch(f"/api/v1/me/files/{file_id}", json=body)

    def get_file_text(self, file_id: str) -> dict:
        return self._get(f"/api/v1/me/files/{file_id}/text")

    def download_file(self, file_id: str) -> bytes:
        return self._request("GET", f"/api/v1/me/files/{file_id}/download").content

    # --- The user's cloud computer (read-through machine filesystem) ---

    def machine_fs_list(self, path: str) -> list[dict]:
        data = self._get("/api/v1/me/machine/fs", path=path)
        return data["entries"]

    def machine_fs_read(self, path: str) -> bytes:
        import base64

        data = self._get("/api/v1/me/machine/fs/file", path=path)
        if "text" in data:
            return data["text"].encode()
        return base64.b64decode(data["content_base64"])

    # --- Sources (unified VFS: native files/sessions + connected sources) ---

    def list_sources(self) -> list:
        return self._list("/api/v1/me/sources", "sources")

    def add_source(
        self,
        source_type: str,
        external_ref: str | None = None,
        display_name: str | None = None,
    ) -> dict:
        body: dict = {"source_type": source_type}
        if external_ref:
            body["external_ref"] = external_ref
        if display_name:
            body["display_name"] = display_name
        return self._post("/api/v1/me/sources", json=body)

    def sync_source(self, source_id: str) -> dict:
        return self._post(f"/api/v1/me/sources/{source_id}/sync")

    def delete_source(self, source_id: str) -> None:
        self._delete(f"/api/v1/me/sources/{source_id}")

    def sources_tree(self, depth: int = 3) -> list:
        return self._list("/api/v1/me/sources/tree", "sources", depth=depth)

    def list_source_entries(self, source: str, path: str = "") -> list:
        return self._list(f"/api/v1/me/sources/{source}/entries", "entries", path=path)

    def list_source_entries_page(
        self, source: str, path: str = "", after: str = ""
    ) -> tuple[list, bool]:
        """One page of a source's entries, reporting whether more pages exist.

        We ask for one row beyond the page size; if it comes back, more rows
        exist. `after` is the keyset cursor: pass the last path of the previous
        page to fetch the next one."""
        data = self._get(
            f"/api/v1/me/sources/{source}/entries",
            path=path,
            limit=SOURCE_ENTRIES_PAGE + 1,
            after=after,
        )
        entries = data.get("entries", []) if isinstance(data, dict) else data
        truncated = len(entries) > SOURCE_ENTRIES_PAGE
        return entries[:SOURCE_ENTRIES_PAGE], truncated

    def read_source_doc(self, source: str, ref: str) -> dict:
        return self._get(f"/api/v1/me/sources/{source}/doc", ref=ref)

    def search_sources(self, query: str, source: str | None = None, limit: int = 20) -> list:
        params: dict = {"q": query, "limit": limit}
        if source:
            params["source"] = source
        return self._list("/api/v1/me/sources/search", "results", **params)

    # --- Tables ---

    def create_table(self, name: str, description: str = "", columns: list | None = None) -> dict:
        body: dict = {"name": name, "description": description, "columns": columns or []}
        return self._post("/api/v1/me/tables", json=body)

    def list_tables(self) -> list:
        return self._list("/api/v1/me/tables", "tables")

    def get_table(self, table_id: str) -> dict:
        return self._get(f"/api/v1/me/tables/{table_id}")

    def update_table(self, table_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/me/tables/{table_id}", json=kwargs)

    def delete_table(self, table_id: str) -> None:
        self._delete(f"/api/v1/me/tables/{table_id}")

    def all_tables(self) -> list:
        return self._list("/api/v1/me/tables", "tables")

    def list_table_rows(
        self,
        table_id: str,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "",
        sort_order: str = "asc",
        filters: str = "",
    ) -> dict:
        base = "/api/v1/me/tables"
        params: dict = {"limit": limit, "offset": offset, "sort_order": sort_order}
        if sort_by:
            params["sort_by"] = sort_by
        if filters:
            params["filters"] = filters
        return self._get(f"{base}/{table_id}/rows", **params)

    def insert_table_row(self, table_id: str, data: dict) -> dict:
        base = "/api/v1/me/tables"
        return self._post(f"{base}/{table_id}/rows", json={"data": data})

    def insert_table_rows_batch(self, table_id: str, rows: list[dict]) -> dict:
        base = "/api/v1/me/tables"
        return self._post(
            f"{base}/{table_id}/rows/batch", json={"rows": [{"data": r} for r in rows]}
        )

    def update_table_row(self, table_id: str, row_id: str, data: dict) -> dict:
        base = "/api/v1/me/tables"
        return self._patch(f"{base}/{table_id}/rows/{row_id}", json={"data": data})

    def delete_table_row(self, table_id: str, row_id: str) -> None:
        base = "/api/v1/me/tables"
        self._delete(f"{base}/{table_id}/rows/{row_id}")

    def add_table_column(
        self,
        table_id: str,
        name: str,
        col_type: str = "text",
        options: list | None = None,
    ) -> dict:
        base = "/api/v1/me/tables"
        body: dict = {"name": name, "type": col_type}
        if options:
            body["options"] = options
        return self._post(f"{base}/{table_id}/columns", json=body)

    def delete_table_column(self, table_id: str, column_id: str) -> dict:
        base = "/api/v1/me/tables"
        return self._request("DELETE", f"{base}/{table_id}/columns/{column_id}").json()

    # --- Sessions ---

    def delete_session(self, session_row_id: str) -> None:
        self._delete(f"/api/v1/me/sessions/{session_row_id}")

    def get_transcript_events(self, session_id: str) -> list:
        data = self._get(f"/api/v1/me/transcripts/{session_id}/events")
        return data.get("events", []) if isinstance(data, dict) else data

    def export_transcript_jsonl(self, session_id: str) -> str:
        return self._request(
            "GET",
            f"/api/v1/me/transcripts/{session_id}/export.jsonl",
        ).text

    def restore_session(self, session_row_id: str) -> None:
        self._post(f"/api/v1/me/sessions/{session_row_id}/restore")

    def purge_session(self, session_row_id: str) -> None:
        self._delete(f"/api/v1/me/sessions/{session_row_id}/purge")

    # --- Trash ---

    def get_trash(self) -> dict:
        data = self._get("/api/v1/me/trash")
        return data if isinstance(data, dict) else {}

    def publish(
        self,
        title: str,
        content: str,
        content_type: str = "markdown",
        audience: str = "public",
        folder_id: str | None = None,
    ) -> dict:
        body: dict = {
            "title": title,
            "content": content,
            "content_type": content_type,
            "audience": audience,
        }
        if folder_id:
            body["folder_id"] = folder_id
        return self._post("/api/v1/publish", json=body)
