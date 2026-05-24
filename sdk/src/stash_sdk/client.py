"""Stash Python SDK — shared memory for AI agents."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://api.joinstash.ai"


class StashError(Exception):
    def __init__(self, status_code: int, detail: str | list):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


class Stash:
    """Client for the Stash API.

    Args:
        api_key: Stash API key (``mc_...``). Falls back to ``STASH_API_KEY`` env var.
        workspace: Default workspace ID. Falls back to ``STASH_WORKSPACE`` env var.
        base_url: API base URL. Falls back to ``STASH_URL`` env var, then production.
        timeout: Default request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str | None = None,
        workspace: str | None = None,
        base_url: str | None = None,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.environ.get("STASH_API_KEY", "")
        self.workspace = workspace or os.environ.get("STASH_WORKSPACE", "")
        base = (base_url or os.environ.get("STASH_URL", "")).rstrip("/") or DEFAULT_BASE_URL
        self._http = httpx.Client(base_url=base, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # --- internals ---

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = self._http.request(method, path, headers=headers, **kwargs)
        if not resp.is_success:
            detail: str | list = resp.text
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                pass
            raise StashError(resp.status_code, detail)
        return resp

    def _get(self, path: str, **params) -> dict | list:
        return self._request("GET", path, params=params).json()

    def _post(self, path: str, json=None, **kwargs) -> dict:
        resp = self._request("POST", path, json=json, **kwargs)
        return {} if resp.status_code == 204 else resp.json()

    def _put(self, path: str, json=None) -> dict:
        return self._request("PUT", path, json=json).json()

    def _patch(self, path: str, json=None) -> dict:
        return self._request("PATCH", path, json=json).json()

    def _delete(self, path: str) -> None:
        self._request("DELETE", path)

    def _list(self, path: str, key: str, **params) -> list:
        data = self._get(path, **params)
        return data.get(key, data) if isinstance(data, dict) else data

    def _upload(self, path: str, file_path: str | Path) -> dict:
        p = Path(file_path)
        content_type = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        with open(p, "rb") as f:
            resp = self._request(
                "POST",
                path,
                files={"file": (p.name, f, content_type)},
                timeout=300,
            )
        return resp.json()

    def _ws(self, workspace: str | None = None) -> str:
        ws = workspace or self.workspace
        if not ws:
            raise StashError(0, "No workspace configured — pass workspace= or set STASH_WORKSPACE")
        return ws

    # =========================================================================
    # Auth
    # =========================================================================

    def register(
        self, name: str, description: str = "", password: str | None = None
    ) -> dict:
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

    # =========================================================================
    # Workspaces
    # =========================================================================

    def create_workspace(self, name: str, description: str = "") -> dict:
        return self._post(
            "/api/v1/workspaces",
            json={"name": name, "description": description},
        )

    def list_workspaces(self, mine: bool = False) -> list:
        path = "/api/v1/workspaces/mine" if mine else "/api/v1/workspaces"
        return self._list(path, "workspaces")

    def get_workspace(self, workspace: str | None = None) -> dict:
        return self._get(f"/api/v1/workspaces/{self._ws(workspace)}")

    def join_workspace(self, invite_code: str) -> dict:
        return self._post(f"/api/v1/workspaces/join/{invite_code}")

    def leave_workspace(self, workspace: str | None = None) -> None:
        self._post(f"/api/v1/workspaces/{self._ws(workspace)}/leave")

    def workspace_members(self, workspace: str | None = None) -> list:
        return self._get(f"/api/v1/workspaces/{self._ws(workspace)}/members")

    def workspace_public_info(self, workspace: str | None = None) -> dict:
        return self._get(f"/api/v1/workspaces/{self._ws(workspace)}/public-info")

    def create_join_request(self, workspace: str | None = None) -> dict:
        return self._post(f"/api/v1/workspaces/{self._ws(workspace)}/join-requests")

    def get_my_join_request(self, workspace: str | None = None) -> dict | None:
        try:
            return self._get(f"/api/v1/workspaces/{self._ws(workspace)}/join-requests/mine")
        except StashError as e:
            if e.status_code == 404:
                return None
            raise

    # =========================================================================
    # Discover (public Stashes)
    # =========================================================================

    def list_discover_stashes(
        self,
        query: str = "",
        sort: str = "trending",
        limit: int = 48,
    ) -> dict:
        params: dict = {"sort": sort, "limit": limit}
        if query:
            params["q"] = query
        return self._get("/api/v1/discover/stashes", **params)

    # =========================================================================
    # Stashes
    # =========================================================================

    def list_stashes(self, workspace: str | None = None) -> list:
        return self._list(f"/api/v1/workspaces/{self._ws(workspace)}/stashes", "stashes")

    def create_stash(
        self,
        title: str,
        description: str = "",
        access: str = "workspace",
        discoverable: bool = False,
        cover_image_url: str | None = None,
        items: list | None = None,
        workspace: str | None = None,
    ) -> dict:
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/stashes",
            json={
                "title": title,
                "description": description,
                "access": access,
                "discoverable": discoverable,
                "cover_image_url": cover_image_url,
                "items": items or [],
            },
        )

    def publish_stash(
        self,
        title: str,
        description: str = "",
        discoverable: bool = False,
        cover_image_url: str | None = None,
        items: list | None = None,
        workspace: str | None = None,
    ) -> dict:
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/stashes/publish",
            json={
                "title": title,
                "description": description,
                "access": "public",
                "discoverable": discoverable,
                "cover_image_url": cover_image_url,
                "items": items or [],
            },
        )

    def update_stash(self, stash_id: str, **fields) -> dict:
        return self._patch(f"/api/v1/stashes/{stash_id}", json=fields)

    def delete_stash(self, stash_id: str) -> None:
        self._delete(f"/api/v1/stashes/{stash_id}")

    def get_public_stash(self, slug: str) -> dict:
        return self._get(f"/api/v1/stashes/{slug}")

    def get_stash_text(self, slug: str) -> str:
        resp = self._request("GET", f"/api/v1/stashes/{slug}", params={"format": "text"})
        return resp.text

    def add_stash_to_workspace(self, slug: str, workspace: str | None = None) -> dict:
        return self._post(
            f"/api/v1/stashes/{slug}/add-to-workspace",
            json={"workspace_id": self._ws(workspace)},
        )

    # =========================================================================
    # Invite tokens
    # =========================================================================

    def create_invite_token(
        self, workspace: str | None = None, max_uses: int = 1, ttl_days: int = 7
    ) -> dict:
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/invite-tokens",
            json={"max_uses": max_uses, "ttl_days": ttl_days},
        )

    def list_invite_tokens(self, workspace: str | None = None) -> list:
        return self._list(
            f"/api/v1/workspaces/{self._ws(workspace)}/invite-tokens", "tokens"
        )

    def revoke_invite_token(self, token_id: str, workspace: str | None = None) -> None:
        self._delete(f"/api/v1/workspaces/{self._ws(workspace)}/invite-tokens/{token_id}")

    def redeem_invite_authed(self, token: str) -> dict:
        return self._post("/api/v1/workspaces/redeem-invite", json={"token": token})

    @staticmethod
    def redeem_invite_unauthenticated(
        base_url: str, token: str, display_name: str
    ) -> dict:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/api/v1/users/cli-auth/redeem-invite",
            json={"token": token, "display_name": display_name},
            timeout=30,
            follow_redirects=True,
        )
        if not resp.is_success:
            detail: str | list = resp.text
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                pass
            raise StashError(resp.status_code, detail)
        return resp.json()

    # =========================================================================
    # Aggregate (cross-workspace)
    # =========================================================================

    def all_pages(self) -> list:
        return self._list("/api/v1/me/pages", "pages")

    def all_events(
        self,
        agent_name: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list:
        params: dict = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        return self._list("/api/v1/me/session-events", "events", **params)

    def all_tables(self) -> list:
        return self._list("/api/v1/me/tables", "tables")

    # =========================================================================
    # Folders (workspace-scoped, nestable)
    # =========================================================================

    def list_folders(self, workspace: str | None = None) -> list:
        return self._list(
            f"/api/v1/workspaces/{self._ws(workspace)}/folders", "folders"
        )

    def create_folder(
        self,
        name: str,
        parent_folder_id: str | None = None,
        workspace: str | None = None,
    ) -> dict:
        body: dict = {"name": name}
        if parent_folder_id:
            body["parent_folder_id"] = parent_folder_id
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/folders", json=body
        )

    def delete_folder(self, folder_id: str, workspace: str | None = None) -> None:
        self._delete(f"/api/v1/workspaces/{self._ws(workspace)}/folders/{folder_id}")

    def get_workspace_tree(self, workspace: str | None = None) -> dict:
        return self._get(f"/api/v1/workspaces/{self._ws(workspace)}/tree")

    # =========================================================================
    # Pages (workspace-scoped)
    # =========================================================================

    def create_page(
        self,
        name: str,
        content: str = "",
        folder_id: str | None = None,
        content_type: str = "markdown",
        content_html: str = "",
        workspace: str | None = None,
    ) -> dict:
        body: dict = {
            "name": name,
            "content": content,
            "content_type": content_type,
            "content_html": content_html,
        }
        if folder_id:
            body["folder_id"] = folder_id
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/pages/new",
            json=body,
        )

    def list_pages(self, workspace: str | None = None) -> list:
        return self._list(
            f"/api/v1/workspaces/{self._ws(workspace)}/pages", "pages"
        )

    def get_page(self, page_id: str, workspace: str | None = None) -> dict:
        return self._get(
            f"/api/v1/workspaces/{self._ws(workspace)}/pages/{page_id}"
        )

    def update_page(
        self, page_id: str, workspace: str | None = None, **kwargs
    ) -> dict:
        return self._patch(
            f"/api/v1/workspaces/{self._ws(workspace)}/pages/{page_id}",
            json=kwargs,
        )

    def delete_page(self, page_id: str, workspace: str | None = None) -> None:
        self._delete(
            f"/api/v1/workspaces/{self._ws(workspace)}/pages/{page_id}"
        )

    # =========================================================================
    # Session events
    # =========================================================================

    def push_event(
        self,
        agent_name: str,
        event_type: str,
        content: str,
        session_id: str | None = None,
        default_stash_id: str | None = None,
        tool_name: str | None = None,
        metadata: dict | None = None,
        attachments: list[dict] | None = None,
        created_at: str | None = None,
        workspace: str | None = None,
    ) -> dict:
        body: dict = {
            "agent_name": agent_name,
            "event_type": event_type,
            "content": content,
        }
        if session_id:
            body["session_id"] = session_id
        if default_stash_id:
            body["default_stash_id"] = default_stash_id
        if tool_name:
            body["tool_name"] = tool_name
        if metadata:
            body["metadata"] = metadata
        if attachments:
            body["attachments"] = attachments
        if created_at:
            body["created_at"] = created_at
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/sessions/events", json=body
        )

    def push_events_batch(
        self,
        events: list[dict],
        workspace: str | None = None,
        default_stash_id: str | None = None,
    ) -> list:
        body: dict = {"events": events}
        if default_stash_id:
            body["default_stash_id"] = default_stash_id
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/sessions/events/batch",
            json=body,
        )

    def query_events(
        self,
        agent_name: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        after: str | None = None,
        workspace: str | None = None,
    ) -> list:
        params: dict = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        if after:
            params["after"] = after
        return self._list(
            f"/api/v1/workspaces/{self._ws(workspace)}/sessions/events", "events", **params
        )

    def search_events(
        self, query: str, limit: int = 50, workspace: str | None = None
    ) -> list:
        return self._list(
            f"/api/v1/workspaces/{self._ws(workspace)}/sessions/events/search",
            "events",
            q=query,
            limit=limit,
        )

    def list_agent_names(self, workspace: str | None = None) -> list:
        data = self._get(
            f"/api/v1/workspaces/{self._ws(workspace)}/sessions/agent-names"
        )
        return data.get("agent_names", []) if isinstance(data, dict) else data

    def upload_transcript(
        self,
        session_id: str,
        transcript_path: str | Path,
        agent_name: str,
        cwd: str = "",
        workspace: str | None = None,
        default_stash_id: str | None = None,
        replace: bool = False,
    ) -> dict:
        import gzip as _gzip

        with open(transcript_path, "rb") as f:
            raw = f.read()
        body = _gzip.compress(raw)
        name = os.path.basename(str(transcript_path))
        if not name.endswith(".gz"):
            name += ".gz"
        resp = self._request(
            "POST",
            f"/api/v1/workspaces/{self._ws(workspace)}/transcripts",
            data={
                "session_id": session_id,
                "agent_name": agent_name,
                "cwd": cwd,
                "replace": str(replace).lower(),
                **({"default_stash_id": default_stash_id} if default_stash_id else {}),
            },
            files={"file": (name, body, "application/gzip")},
            timeout=120,
        )
        return resp.json()

    # =========================================================================
    # Files
    # =========================================================================

    def upload_file(self, file_path: str | Path, workspace: str | None = None) -> dict:
        return self._upload(
            f"/api/v1/workspaces/{self._ws(workspace)}/files", file_path
        )

    def list_files(self, workspace: str | None = None) -> list:
        return self._list(
            f"/api/v1/workspaces/{self._ws(workspace)}/files", "files"
        )

    def get_file(self, file_id: str, workspace: str | None = None) -> dict:
        return self._get(
            f"/api/v1/workspaces/{self._ws(workspace)}/files/{file_id}"
        )

    def delete_file(self, file_id: str, workspace: str | None = None) -> None:
        self._delete(f"/api/v1/workspaces/{self._ws(workspace)}/files/{file_id}")

    def get_file_text(self, file_id: str, workspace: str | None = None) -> dict:
        return self._get(
            f"/api/v1/workspaces/{self._ws(workspace)}/files/{file_id}/text"
        )

    # =========================================================================
    # Webhooks
    # =========================================================================

    def set_webhook(
        self, url: str, secret: str | None = None, workspace: str | None = None
    ) -> dict:
        body: dict = {"url": url}
        if secret:
            body["secret"] = secret
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/webhooks", json=body
        )

    # =========================================================================
    # Tables
    # =========================================================================

    def create_table(
        self,
        name: str,
        description: str = "",
        columns: list | None = None,
        workspace: str | None = None,
    ) -> dict:
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables",
            json={"name": name, "description": description, "columns": columns or []},
        )

    def list_tables(self, workspace: str | None = None) -> list:
        return self._list(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables", "tables"
        )

    def get_table(self, table_id: str, workspace: str | None = None) -> dict:
        return self._get(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}"
        )

    def update_table(self, table_id: str, workspace: str | None = None, **kwargs) -> dict:
        return self._patch(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}", json=kwargs
        )

    def delete_table(self, table_id: str, workspace: str | None = None) -> None:
        self._delete(f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}")

    def list_table_rows(
        self,
        table_id: str,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "",
        sort_order: str = "asc",
        filters: str = "",
        workspace: str | None = None,
    ) -> dict:
        params: dict = {"limit": limit, "offset": offset, "sort_order": sort_order}
        if sort_by:
            params["sort_by"] = sort_by
        if filters:
            params["filters"] = filters
        return self._get(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}/rows",
            **params,
        )

    def insert_table_row(
        self, table_id: str, data: dict, workspace: str | None = None
    ) -> dict:
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}/rows",
            json={"data": data},
        )

    def insert_table_rows_batch(
        self, table_id: str, rows: list[dict], workspace: str | None = None
    ) -> dict:
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}/rows/batch",
            json={"rows": [{"data": r} for r in rows]},
        )

    def update_table_row(
        self, table_id: str, row_id: str, data: dict, workspace: str | None = None
    ) -> dict:
        return self._patch(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}/rows/{row_id}",
            json={"data": data},
        )

    def delete_table_row(
        self, table_id: str, row_id: str, workspace: str | None = None
    ) -> None:
        self._delete(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}/rows/{row_id}"
        )

    def add_table_column(
        self,
        table_id: str,
        name: str,
        col_type: str = "text",
        options: list | None = None,
        workspace: str | None = None,
    ) -> dict:
        body: dict = {"name": name, "type": col_type}
        if options:
            body["options"] = options
        return self._post(
            f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}/columns",
            json=body,
        )

    def delete_table_column(
        self, table_id: str, column_id: str, workspace: str | None = None
    ) -> dict:
        return self._request(
            "DELETE",
            f"/api/v1/workspaces/{self._ws(workspace)}/tables/{table_id}/columns/{column_id}",
        ).json()
