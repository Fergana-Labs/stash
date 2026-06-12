"""Synchronous httpx client wrapping the Stash REST API."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

import httpx


class StashError(Exception):
    def __init__(self, status_code: int, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


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
        with open(file_path, "rb") as f:
            resp = self._request(
                "POST",
                path,
                files={"file": (filename, f, content_type)},
                data={"folder_id": folder_id} if folder_id else None,
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

    def revoke_api_key(self, key_id: str) -> None:
        self._delete(f"/api/v1/users/me/keys/{key_id}")

    # --- Workspaces ---

    def create_workspace(self, name: str, description: str = "") -> dict:
        return self._post(
            "/api/v1/workspaces",
            json={
                "name": name,
                "description": description,
            },
        )

    def list_workspaces(self) -> list:
        return self._list("/api/v1/workspaces/mine", "workspaces")

    def get_workspace(self, workspace_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}")

    def join_workspace(self, invite_code: str) -> dict:
        return self._post(f"/api/v1/workspaces/join/{invite_code}")

    def leave_workspace(self, workspace_id: str) -> None:
        self._post(f"/api/v1/workspaces/{workspace_id}/leave")

    def workspace_members(self, workspace_id: str) -> list:
        return self._get(f"/api/v1/workspaces/{workspace_id}/members")

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

    def list_skills(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/skills", "skills")

    def publish_skill_folder(
        self,
        workspace_id: str,
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
        return self._post(f"/api/v1/workspaces/{workspace_id}/skills", json=body)

    def update_skill(self, skill_id: str, **fields) -> dict:
        return self._patch(f"/api/v1/skills/{skill_id}", json=fields)

    def unpublish_skill(self, skill_id: str) -> None:
        self._delete(f"/api/v1/skills/{skill_id}")

    def fork_skill(self, slug: str, workspace_id: str) -> dict:
        return self._post(
            f"/api/v1/skills/{slug}/add-to-workspace",
            json={"workspace_id": workspace_id},
        )

    def get_public_skill(self, slug: str) -> dict:
        return self._get(f"/api/v1/skills/{slug}")

    def get_skill_text(self, slug: str) -> str:
        resp = self._request("GET", f"/api/v1/skills/{slug}", params={"format": "text"})
        return resp.text

    def snapshot_source_into_skill(
        self, workspace_id: str, skill_id: str, source_id: str, path: str
    ) -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/skills/{skill_id}/snapshot-source",
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

    def list_session_folders(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/session-folders", "folders")

    def create_session_folder(self, workspace_id: str, name: str) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/session-folders", json={"name": name})

    def assign_session_folder(
        self, workspace_id: str, session_row_id: str, folder_id: str | None = None
    ) -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/session-folders/assign",
            json={"session_row_id": session_row_id, "folder_id": folder_id},
        )

    # --- Magic-link invite tokens ---

    def create_invite_token(self, workspace_id: str, max_uses: int = 1, ttl_days: int = 7) -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/invite-tokens",
            json={"max_uses": max_uses, "ttl_days": ttl_days},
        )

    def list_invite_tokens(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/invite-tokens", "tokens")

    def revoke_invite_token(self, workspace_id: str, token_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/invite-tokens/{token_id}")

    def redeem_invite_authed(self, token: str) -> dict:
        return self._post("/api/v1/workspaces/redeem-invite", json={"token": token})

    @staticmethod
    def redeem_invite_unauthenticated(base_url: str, token: str, display_name: str) -> dict:
        """One-shot, no api_key required — creates a new user + joins workspace."""
        resp = httpx.post(
            f"{base_url.rstrip('/')}/api/v1/users/cli-auth/redeem-invite",
            json={"token": token, "display_name": display_name},
            timeout=30,
            follow_redirects=True,
        )
        if not resp.is_success:
            detail = ""
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise StashError(resp.status_code, detail)
        return resp.json()

    # --- Aggregate ---

    def all_pages(self) -> list:
        return self._list("/api/v1/me/pages", "pages")

    # --- Folders (workspace-scoped, nestable) ---

    def list_folders(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/folders", "folders")

    def create_folder(
        self,
        workspace_id: str,
        name: str,
        parent_folder_id: str | None = None,
    ) -> dict:
        body: dict = {"name": name}
        if parent_folder_id:
            body["parent_folder_id"] = parent_folder_id
        return self._post(f"/api/v1/workspaces/{workspace_id}/folders", json=body)

    def delete_folder(self, workspace_id: str, folder_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/folders/{folder_id}")

    def copy_folder(
        self, workspace_id: str, folder_id: str, target_folder_id: str | None = None
    ) -> dict:
        body = {"target_folder_id": target_folder_id} if target_folder_id else {}
        return self._post(f"/api/v1/workspaces/{workspace_id}/folders/{folder_id}/copy", json=body)

    def update_folder(
        self,
        workspace_id: str,
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
        return self._patch(
            f"/api/v1/workspaces/{workspace_id}/folders/{folder_id}",
            json=body,
        )

    def get_workspace_tree(self, workspace_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/tree")

    def get_workspace_overview(self, workspace_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/overview")

    # --- Pages (workspace-scoped) ---

    def create_page(
        self,
        workspace_id: str,
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
        return self._post(f"/api/v1/workspaces/{workspace_id}/pages/new", json=body)

    def list_pages(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/pages", "pages")

    def get_page(self, workspace_id: str, page_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/pages/{page_id}")

    def update_page(self, workspace_id: str, page_id: str, **kwargs) -> dict:
        return self._patch(
            f"/api/v1/workspaces/{workspace_id}/pages/{page_id}",
            json=kwargs,
        )

    def delete_page(self, workspace_id: str, page_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/pages/{page_id}")

    def restore_page(self, workspace_id: str, page_id: str) -> None:
        self._post(f"/api/v1/workspaces/{workspace_id}/pages/{page_id}/restore")

    def purge_page(self, workspace_id: str, page_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/pages/{page_id}/purge")

    def copy_page(
        self, workspace_id: str, page_id: str, target_folder_id: str | None = None
    ) -> dict:
        body = {"target_folder_id": target_folder_id} if target_folder_id else {}
        return self._post(f"/api/v1/workspaces/{workspace_id}/pages/{page_id}/copy", json=body)

    # --- Session events ---

    def list_agent_names(self, workspace_id: str) -> list:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/sessions/agent-names")
        return data.get("agent_names", []) if isinstance(data, dict) else data

    def push_event(
        self,
        workspace_id: str,
        agent_name: str,
        event_type: str,
        content: str,
        session_id: str | None = None,
        tool_name: str | None = None,
        metadata: dict | None = None,
        attachments: list[dict] | None = None,
        created_at: str | None = None,
    ) -> dict:
        body: dict = {"agent_name": agent_name, "event_type": event_type, "content": content}
        if session_id:
            body["session_id"] = session_id
        if tool_name:
            body["tool_name"] = tool_name
        if metadata:
            body["metadata"] = metadata
        if attachments:
            body["attachments"] = attachments
        if created_at:
            body["created_at"] = created_at
        return self._post(f"/api/v1/workspaces/{workspace_id}/sessions/events", json=body)

    def query_events(
        self,
        workspace_id: str,
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
        return self._list(f"/api/v1/workspaces/{workspace_id}/sessions/events", "events", **params)

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

    def push_events_batch(
        self,
        workspace_id: str,
        events: list[dict],
    ) -> list:
        body: dict = {"events": events}
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/sessions/events/batch",
            json=body,
        )

    def upload_transcript(
        self,
        workspace_id: str,
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
        resp = self._request(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/transcripts",
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

    # --- Files ---

    def upload_ws_file(
        self, workspace_id: str, file_path: str, folder_id: str | None = None
    ) -> dict:
        return self._upload(f"/api/v1/workspaces/{workspace_id}/files", file_path, folder_id)

    def list_ws_files(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/files", "files")

    def get_ws_file(self, workspace_id: str, file_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/files/{file_id}")

    def delete_ws_file(self, workspace_id: str, file_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/files/{file_id}")

    def copy_ws_file(
        self, workspace_id: str, file_id: str, target_folder_id: str | None = None
    ) -> dict:
        body = {"target_folder_id": target_folder_id} if target_folder_id else {}
        return self._post(f"/api/v1/workspaces/{workspace_id}/files/{file_id}/copy", json=body)

    # --- Batch ops (best-effort move/delete/restore over many items) ---

    def batch_move(
        self,
        workspace_id: str,
        items: list[dict],
        target_folder_id: str | None = None,
        move_to_root: bool = False,
    ) -> dict:
        body: dict = {"items": items, "move_to_root": move_to_root}
        if target_folder_id:
            body["target_folder_id"] = target_folder_id
        return self._post(f"/api/v1/workspaces/{workspace_id}/batch/move", json=body)

    def batch_delete(self, workspace_id: str, items: list[dict]) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/batch/delete", json={"items": items})

    def batch_restore(self, workspace_id: str, items: list[dict]) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/batch/restore", json={"items": items})

    def restore_ws_file(self, workspace_id: str, file_id: str) -> None:
        self._post(f"/api/v1/workspaces/{workspace_id}/files/{file_id}/restore")

    def purge_ws_file(self, workspace_id: str, file_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/files/{file_id}/purge")

    def update_ws_file(
        self,
        workspace_id: str,
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
        return self._patch(
            f"/api/v1/workspaces/{workspace_id}/files/{file_id}",
            json=body,
        )

    def get_ws_file_text(self, workspace_id: str, file_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/files/{file_id}/text")

    def download_ws_file(self, workspace_id: str, file_id: str) -> bytes:
        return self._request(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/files/{file_id}/download",
        ).content

    # --- Sources (unified VFS: native files/sessions + connected sources) ---

    def list_sources(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/sources", "sources")

    def add_source(
        self,
        workspace_id: str,
        source_type: str,
        external_ref: str | None = None,
        display_name: str | None = None,
    ) -> dict:
        body: dict = {"source_type": source_type}
        if external_ref:
            body["external_ref"] = external_ref
        if display_name:
            body["display_name"] = display_name
        return self._post(f"/api/v1/workspaces/{workspace_id}/sources", json=body)

    def sync_source(self, workspace_id: str, source_id: str) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/sync")

    def delete_source(self, workspace_id: str, source_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/sources/{source_id}")

    def sources_tree(self, workspace_id: str, depth: int = 3) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/sources/tree", "sources", depth=depth)

    def list_source_entries(self, workspace_id: str, source: str, path: str = "") -> list:
        return self._list(
            f"/api/v1/workspaces/{workspace_id}/sources/{source}/entries", "entries", path=path
        )

    def read_source_doc(self, workspace_id: str, source: str, ref: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/sources/{source}/doc", ref=ref)

    def search_sources(
        self, workspace_id: str, query: str, source: str | None = None, limit: int = 20
    ) -> list:
        params: dict = {"q": query, "limit": limit}
        if source:
            params["source"] = source
        return self._list(f"/api/v1/workspaces/{workspace_id}/sources/search", "results", **params)

    # --- Tables ---

    def create_table(
        self, workspace_id: str, name: str, description: str = "", columns: list | None = None
    ) -> dict:
        body: dict = {"name": name, "description": description, "columns": columns or []}
        return self._post(f"/api/v1/workspaces/{workspace_id}/tables", json=body)

    def list_tables(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/tables", "tables")

    def get_table(self, workspace_id: str, table_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/tables/{table_id}")

    def update_table(self, workspace_id: str, table_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/workspaces/{workspace_id}/tables/{table_id}", json=kwargs)

    def delete_table(self, workspace_id: str, table_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/tables/{table_id}")

    def all_tables(self) -> list:
        return self._list("/api/v1/me/tables", "tables")

    def list_table_rows(
        self,
        workspace_id: str,
        table_id: str,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "",
        sort_order: str = "asc",
        filters: str = "",
    ) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables"
        params: dict = {"limit": limit, "offset": offset, "sort_order": sort_order}
        if sort_by:
            params["sort_by"] = sort_by
        if filters:
            params["filters"] = filters
        return self._get(f"{base}/{table_id}/rows", **params)

    def insert_table_row(self, workspace_id: str, table_id: str, data: dict) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables"
        return self._post(f"{base}/{table_id}/rows", json={"data": data})

    def insert_table_rows_batch(self, workspace_id: str, table_id: str, rows: list[dict]) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables"
        return self._post(
            f"{base}/{table_id}/rows/batch", json={"rows": [{"data": r} for r in rows]}
        )

    def update_table_row(self, workspace_id: str, table_id: str, row_id: str, data: dict) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables"
        return self._patch(f"{base}/{table_id}/rows/{row_id}", json={"data": data})

    def delete_table_row(self, workspace_id: str, table_id: str, row_id: str) -> None:
        base = f"/api/v1/workspaces/{workspace_id}/tables"
        self._delete(f"{base}/{table_id}/rows/{row_id}")

    def add_table_column(
        self,
        workspace_id: str,
        table_id: str,
        name: str,
        col_type: str = "text",
        options: list | None = None,
    ) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables"
        body: dict = {"name": name, "type": col_type}
        if options:
            body["options"] = options
        return self._post(f"{base}/{table_id}/columns", json=body)

    def delete_table_column(self, workspace_id: str, table_id: str, column_id: str) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables"
        return self._request("DELETE", f"{base}/{table_id}/columns/{column_id}").json()

    # --- Sessions ---

    def delete_session(self, workspace_id: str, session_row_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/sessions/{session_row_id}")

    def get_transcript_events(self, workspace_id: str, session_id: str) -> list:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/transcripts/{session_id}/events")
        return data.get("events", []) if isinstance(data, dict) else data

    def export_transcript_jsonl(self, workspace_id: str, session_id: str) -> str:
        return self._request(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/transcripts/{session_id}/export.jsonl",
        ).text

    def restore_session(self, workspace_id: str, session_row_id: str) -> None:
        self._post(f"/api/v1/workspaces/{workspace_id}/sessions/{session_row_id}/restore")

    def purge_session(self, workspace_id: str, session_row_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/sessions/{session_row_id}/purge")

    # --- Trash ---

    def get_trash(self, workspace_id: str) -> dict:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/trash")
        return data if isinstance(data, dict) else {}

    def publish(
        self,
        workspace_id: str,
        title: str,
        content: str,
        content_type: str = "markdown",
        audience: str = "public",
        folder_id: str | None = None,
    ) -> dict:
        body: dict = {
            "workspace_id": workspace_id,
            "title": title,
            "content": content,
            "content_type": content_type,
            "audience": audience,
        }
        if folder_id:
            body["folder_id"] = folder_id
        return self._post("/api/v1/publish", json=body)
