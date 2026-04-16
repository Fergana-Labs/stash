"""Synchronous httpx client wrapping the Stash REST API."""

from __future__ import annotations

import httpx


class StashError(Exception):
    def __init__(self, status_code: int, detail: str):
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

    def _get(self, path: str, **params) -> dict | list:
        return self._request("GET", path, params=params).json()

    def _post(self, path: str, json=None) -> dict:
        resp = self._request("POST", path, json=json)
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

    # --- Workspaces ---

    def create_workspace(self, name: str, description: str = "", is_public: bool = False) -> dict:
        return self._post(
            "/api/v1/workspaces",
            json={
                "name": name,
                "description": description,
                "is_public": is_public,
            },
        )

    def list_workspaces(self, mine: bool = False) -> list:
        path = "/api/v1/workspaces/mine" if mine else "/api/v1/workspaces"
        return self._list(path, "workspaces")

    def get_workspace(self, workspace_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}")

    def join_workspace(self, invite_code: str) -> dict:
        return self._post(f"/api/v1/workspaces/join/{invite_code}")

    def leave_workspace(self, workspace_id: str) -> None:
        self._post(f"/api/v1/workspaces/{workspace_id}/leave")

    def workspace_members(self, workspace_id: str) -> list:
        return self._get(f"/api/v1/workspaces/{workspace_id}/members")

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

    # --- Chats (workspace-scoped) ---

    def create_chat(self, workspace_id: str, name: str, description: str = "") -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/chats",
            json={
                "name": name,
                "description": description,
            },
        )

    def list_chats(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/chats", "chats")

    def send_message(self, workspace_id: str, chat_id: str, content: str) -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages",
            json={"content": content},
        )

    def read_messages(
        self, workspace_id: str, chat_id: str, limit: int = 50, after: str | None = None
    ) -> list:
        params: dict = {"limit": limit}
        if after:
            params["after"] = after
        return self._list(
            f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages", "messages", **params
        )

    def search_messages(self, workspace_id: str, chat_id: str, query: str, limit: int = 20) -> list:
        return self._list(
            f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages/search",
            "messages",
            q=query,
            limit=limit,
        )

    # --- Personal Rooms ---

    def create_room(self, name: str, description: str = "") -> dict:
        return self._post("/api/v1/rooms", json={"name": name, "description": description})

    def list_rooms(self) -> list:
        return self._list("/api/v1/rooms", "chats")

    def send_room_message(self, room_id: str, content: str) -> dict:
        return self._post(f"/api/v1/rooms/{room_id}/messages", json={"content": content})

    def read_room_messages(self, room_id: str, limit: int = 50, after: str | None = None) -> list:
        params: dict = {"limit": limit}
        if after:
            params["after"] = after
        return self._list(f"/api/v1/rooms/{room_id}/messages", "messages", **params)

    def delete_room(self, room_id: str) -> None:
        self._delete(f"/api/v1/rooms/{room_id}")

    # --- DMs ---

    def start_dm(self, username: str) -> dict:
        return self._post("/api/v1/dms", json={"username": username})

    def list_dms(self) -> list:
        return self._list("/api/v1/dms", "dms")

    def send_dm(self, username: str, content: str) -> dict:
        dm = self.start_dm(username)
        return self._post(f"/api/v1/dms/{dm['id']}/messages", json={"content": content})

    def read_dm_messages(self, chat_id: str, limit: int = 50, after: str | None = None) -> list:
        params: dict = {"limit": limit}
        if after:
            params["after"] = after
        return self._list(f"/api/v1/dms/{chat_id}/messages", "messages", **params)

    # --- Aggregate ---

    def all_chats(self) -> dict:
        return self._get("/api/v1/me/chats")

    def all_notebooks(self) -> list:
        return self._list("/api/v1/me/notebooks", "notebooks")

    def all_decks(self) -> list:
        return self._list("/api/v1/me/decks", "decks")

    # --- Notebooks (collections) ---

    def create_notebook(self, workspace_id: str, name: str, description: str = "") -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/notebooks",
            json={
                "name": name,
                "description": description,
            },
        )

    def list_notebooks(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/notebooks", "notebooks")

    def delete_notebook(self, workspace_id: str, notebook_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}")

    def create_personal_notebook(self, name: str, description: str = "") -> dict:
        return self._post("/api/v1/notebooks", json={"name": name, "description": description})

    def list_personal_notebooks(self) -> list:
        return self._list("/api/v1/notebooks", "notebooks")

    # --- Notebook Pages ---

    def create_page(
        self,
        workspace_id: str,
        notebook_id: str,
        name: str,
        content: str = "",
        folder_id: str | None = None,
    ) -> dict:
        body: dict = {"name": name, "content": content}
        if folder_id:
            body["folder_id"] = folder_id
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages", json=body
        )

    def list_page_tree(self, workspace_id: str, notebook_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages")

    def get_page(self, workspace_id: str, notebook_id: str, page_id: str) -> dict:
        return self._get(
            f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}"
        )

    def update_page(self, workspace_id: str, notebook_id: str, page_id: str, **kwargs) -> dict:
        return self._patch(
            f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}",
            json=kwargs,
        )

    def delete_page(self, workspace_id: str, notebook_id: str, page_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}")

    def create_personal_page(self, notebook_id: str, name: str, content: str = "") -> dict:
        return self._post(
            f"/api/v1/notebooks/{notebook_id}/pages", json={"name": name, "content": content}
        )

    def list_personal_page_tree(self, notebook_id: str) -> dict:
        return self._get(f"/api/v1/notebooks/{notebook_id}/pages")

    def get_personal_page(self, notebook_id: str, page_id: str) -> dict:
        return self._get(f"/api/v1/notebooks/{notebook_id}/pages/{page_id}")

    def update_personal_page(self, notebook_id: str, page_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/notebooks/{notebook_id}/pages/{page_id}", json=kwargs)

    # --- Notebook Folders ---

    def create_folder(self, workspace_id: str, notebook_id: str, name: str) -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/folders",
            json={"name": name},
        )

    def create_personal_folder(self, notebook_id: str, name: str) -> dict:
        return self._post(f"/api/v1/notebooks/{notebook_id}/folders", json={"name": name})

    # --- History (workspace events) ---

    def list_agent_names(self, workspace_id: str) -> list:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/memory/agent-names")
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
    ) -> dict:
        body: dict = {"agent_name": agent_name, "event_type": event_type, "content": content}
        if session_id:
            body["session_id"] = session_id
        if tool_name:
            body["tool_name"] = tool_name
        if metadata:
            body["metadata"] = metadata
        return self._post(f"/api/v1/workspaces/{workspace_id}/memory/events", json=body)

    def query_events(
        self,
        workspace_id: str,
        agent_name: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        after: str | None = None,
    ) -> list:
        params: dict = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        if after:
            params["after"] = after
        return self._list(f"/api/v1/workspaces/{workspace_id}/memory/events", "events", **params)

    def search_events(self, workspace_id: str, query: str, limit: int = 50) -> list:
        return self._list(
            f"/api/v1/workspaces/{workspace_id}/memory/events/search",
            "events",
            q=query,
            limit=limit,
        )

    def all_events(
        self, agent_name: str | None = None, event_type: str | None = None, limit: int = 50
    ) -> list:
        params: dict = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        return self._list("/api/v1/me/history-events", "events", **params)

    # --- Decks ---

    def create_deck(
        self,
        workspace_id: str,
        name: str,
        description: str = "",
        html_content: str = "",
        deck_type: str = "freeform",
    ) -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/decks",
            json={
                "name": name,
                "description": description,
                "html_content": html_content,
                "deck_type": deck_type,
            },
        )

    def list_decks(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/decks", "decks")

    def get_deck(self, workspace_id: str, deck_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/decks/{deck_id}")

    def update_deck(self, workspace_id: str, deck_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/workspaces/{workspace_id}/decks/{deck_id}", json=kwargs)

    def delete_deck(self, workspace_id: str, deck_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/decks/{deck_id}")

    def create_personal_deck(
        self, name: str, description: str = "", html_content: str = "", deck_type: str = "freeform"
    ) -> dict:
        return self._post(
            "/api/v1/decks",
            json={
                "name": name,
                "description": description,
                "html_content": html_content,
                "deck_type": deck_type,
            },
        )

    def list_personal_decks(self) -> list:
        return self._list("/api/v1/decks", "decks")

    def get_personal_deck(self, deck_id: str) -> dict:
        return self._get(f"/api/v1/decks/{deck_id}")

    def update_personal_deck(self, deck_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/decks/{deck_id}", json=kwargs)

    # --- Deck Share Links ---

    def create_deck_share(self, deck_id: str, workspace_id: str | None = None, **kwargs) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/decks" if workspace_id else "/api/v1/decks"
        return self._post(f"{base}/{deck_id}/shares", json=kwargs)

    def list_deck_shares(self, deck_id: str, workspace_id: str | None = None) -> list:
        base = f"/api/v1/workspaces/{workspace_id}/decks" if workspace_id else "/api/v1/decks"
        return self._list(f"{base}/{deck_id}/shares", "shares")

    def update_deck_share(
        self, deck_id: str, share_id: str, workspace_id: str | None = None, **kwargs
    ) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/decks" if workspace_id else "/api/v1/decks"
        return self._put(f"{base}/{deck_id}/shares/{share_id}", json=kwargs)

    def get_share_analytics(
        self, deck_id: str, share_id: str, workspace_id: str | None = None
    ) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/decks" if workspace_id else "/api/v1/decks"
        return self._get(f"{base}/{deck_id}/shares/{share_id}/analytics")

    # --- Webhooks ---

    def set_webhook(self, workspace_id: str, url: str, secret: str | None = None) -> dict:
        body: dict = {"url": url}
        if secret:
            body["secret"] = secret
        return self._post(f"/api/v1/workspaces/{workspace_id}/webhooks", json=body)

    def search_users(self, query: str) -> list:
        return self._get("/api/v1/dms/users/search", q=query)

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

    def create_personal_table(
        self, name: str, description: str = "", columns: list | None = None
    ) -> dict:
        body: dict = {"name": name, "description": description, "columns": columns or []}
        return self._post("/api/v1/tables", json=body)

    def list_personal_tables(self) -> list:
        return self._list("/api/v1/tables", "tables")

    def all_tables(self) -> list:
        return self._list("/api/v1/me/tables", "tables")

    def list_table_rows(
        self,
        workspace_id: str | None,
        table_id: str,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "",
        sort_order: str = "asc",
        filters: str = "",
    ) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        params: dict = {"limit": limit, "offset": offset, "sort_order": sort_order}
        if sort_by:
            params["sort_by"] = sort_by
        if filters:
            params["filters"] = filters
        return self._get(f"{base}/{table_id}/rows", **params)

    def insert_table_row(self, workspace_id: str | None, table_id: str, data: dict) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        return self._post(f"{base}/{table_id}/rows", json={"data": data})

    def insert_table_rows_batch(
        self, workspace_id: str | None, table_id: str, rows: list[dict]
    ) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        return self._post(
            f"{base}/{table_id}/rows/batch", json={"rows": [{"data": r} for r in rows]}
        )

    def update_table_row(
        self, workspace_id: str | None, table_id: str, row_id: str, data: dict
    ) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        return self._patch(f"{base}/{table_id}/rows/{row_id}", json={"data": data})

    def delete_table_row(self, workspace_id: str | None, table_id: str, row_id: str) -> None:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        self._delete(f"{base}/{table_id}/rows/{row_id}")

    def add_table_column(
        self,
        workspace_id: str | None,
        table_id: str,
        name: str,
        col_type: str = "text",
        options: list | None = None,
    ) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        body: dict = {"name": name, "type": col_type}
        if options:
            body["options"] = options
        return self._post(f"{base}/{table_id}/columns", json=body)

    def delete_table_column(self, workspace_id: str | None, table_id: str, column_id: str) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        return self._request("DELETE", f"{base}/{table_id}/columns/{column_id}").json()
