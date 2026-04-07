"""Synchronous httpx client wrapping the Octopus REST API."""

from __future__ import annotations

import httpx


class OctopusError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


class OctopusClient:
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
            raise OctopusError(resp.status_code, detail)
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

    def register(self, name: str, user_type: str = "human", description: str = "", password: str | None = None) -> dict:
        body: dict = {"name": name, "type": user_type, "description": description}
        if password:
            body["password"] = password
        return self._post("/api/v1/users/register", json=body)

    def login(self, name: str, password: str) -> dict:
        return self._post("/api/v1/users/login", json={"name": name, "password": password})

    def whoami(self) -> dict:
        return self._get("/api/v1/users/me")

    # --- Persona Identities ---

    def create_persona(self, name: str, display_name: str = "", description: str = "") -> dict:
        body: dict = {"name": name, "description": description}
        if display_name:
            body["display_name"] = display_name
        return self._post("/api/v1/personas", json=body)

    def list_personas(self) -> list:
        return self._get("/api/v1/personas")

    def rotate_persona_key(self, persona_id: str) -> dict:
        return self._post(f"/api/v1/personas/{persona_id}/rotate-key")

    def delete_persona(self, persona_id: str) -> None:
        self._delete(f"/api/v1/personas/{persona_id}")

    def list_personas_with_context(self) -> list:
        return self._list("/api/v1/me/personas", "personas")

    # --- Workspaces ---

    def create_workspace(self, name: str, description: str = "", is_public: bool = False) -> dict:
        return self._post("/api/v1/workspaces", json={
            "name": name, "description": description, "is_public": is_public,
        })

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

    # --- Chats (workspace-scoped) ---

    def create_chat(self, workspace_id: str, name: str, description: str = "") -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/chats", json={
            "name": name, "description": description,
        })

    def list_chats(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/chats", "chats")

    def send_message(self, workspace_id: str, chat_id: str, content: str) -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages",
            json={"content": content},
        )

    def read_messages(self, workspace_id: str, chat_id: str, limit: int = 50, after: str | None = None) -> list:
        params: dict = {"limit": limit}
        if after:
            params["after"] = after
        return self._list(f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages", "messages", **params)

    def search_messages(self, workspace_id: str, chat_id: str, query: str, limit: int = 20) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages/search", "messages", q=query, limit=limit)

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

    def all_histories(self) -> list:
        return self._list("/api/v1/me/history", "stores")

    def all_decks(self) -> list:
        return self._list("/api/v1/me/decks", "decks")

    # --- Notebooks (collections) ---

    def create_notebook(self, workspace_id: str, name: str, description: str = "") -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/notebooks", json={
            "name": name, "description": description,
        })

    def list_notebooks(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/notebooks", "notebooks")

    def delete_notebook(self, workspace_id: str, notebook_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}")

    def create_personal_notebook(self, name: str, description: str = "") -> dict:
        return self._post("/api/v1/notebooks", json={"name": name, "description": description})

    def list_personal_notebooks(self) -> list:
        return self._list("/api/v1/notebooks", "notebooks")

    # --- Notebook Pages ---

    def create_page(self, workspace_id: str, notebook_id: str, name: str, content: str = "", folder_id: str | None = None) -> dict:
        body: dict = {"name": name, "content": content}
        if folder_id:
            body["folder_id"] = folder_id
        return self._post(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages", json=body)

    def list_page_tree(self, workspace_id: str, notebook_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages")

    def get_page(self, workspace_id: str, notebook_id: str, page_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}")

    def update_page(self, workspace_id: str, notebook_id: str, page_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}", json=kwargs)

    def delete_page(self, workspace_id: str, notebook_id: str, page_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}")

    def create_personal_page(self, notebook_id: str, name: str, content: str = "") -> dict:
        return self._post(f"/api/v1/notebooks/{notebook_id}/pages", json={"name": name, "content": content})

    def list_personal_page_tree(self, notebook_id: str) -> dict:
        return self._get(f"/api/v1/notebooks/{notebook_id}/pages")

    def get_personal_page(self, notebook_id: str, page_id: str) -> dict:
        return self._get(f"/api/v1/notebooks/{notebook_id}/pages/{page_id}")

    def update_personal_page(self, notebook_id: str, page_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/notebooks/{notebook_id}/pages/{page_id}", json=kwargs)

    # --- Notebook Folders ---

    def create_folder(self, workspace_id: str, notebook_id: str, name: str) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/folders", json={"name": name})

    def create_personal_folder(self, notebook_id: str, name: str) -> dict:
        return self._post(f"/api/v1/notebooks/{notebook_id}/folders", json={"name": name})

    # --- Universal Search ---

    def universal_search(self, workspace_id: str, question: str, resource_types: list[str] | None = None) -> dict:
        body: dict = {"question": question}
        if resource_types:
            body["resource_types"] = resource_types
        return self._post(f"/api/v1/workspaces/{workspace_id}/search", json=body)

    def personal_search(self, question: str, resource_types: list[str] | None = None) -> dict:
        body: dict = {"question": question}
        if resource_types:
            body["resource_types"] = resource_types
        return self._post("/api/v1/me/search", json=body)

    # --- History (was memory stores) ---

    def create_history(self, workspace_id: str, name: str, description: str = "") -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/memory", json={
            "name": name, "description": description,
        })

    def list_histories(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/memory", "stores")

    def push_event(
        self, workspace_id: str, store_id: str,
        agent_name: str, event_type: str, content: str,
        session_id: str | None = None, tool_name: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        body: dict = {"agent_name": agent_name, "event_type": event_type, "content": content}
        if session_id:
            body["session_id"] = session_id
        if tool_name:
            body["tool_name"] = tool_name
        if metadata:
            body["metadata"] = metadata
        return self._post(f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events", json=body)

    def query_events(
        self, workspace_id: str, store_id: str,
        agent_name: str | None = None, event_type: str | None = None,
        limit: int = 50, after: str | None = None,
    ) -> list:
        params: dict = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        if after:
            params["after"] = after
        return self._list(f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events", "events", **params)

    def search_events(self, workspace_id: str, store_id: str, query: str, limit: int = 50) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events/search", "events", q=query, limit=limit)

    def query_history(self, workspace_id: str, store_id: str, question: str) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/query", json={"question": question})

    def all_events(self, agent_name: str | None = None, event_type: str | None = None, limit: int = 50) -> list:
        params: dict = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        return self._list("/api/v1/me/history-events", "events", **params)

    # --- Decks ---

    def create_deck(self, workspace_id: str, name: str, description: str = "", html_content: str = "", deck_type: str = "freeform") -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/decks", json={
            "name": name, "description": description, "html_content": html_content, "deck_type": deck_type,
        })

    def list_decks(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/decks", "decks")

    def get_deck(self, workspace_id: str, deck_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/decks/{deck_id}")

    def update_deck(self, workspace_id: str, deck_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/workspaces/{workspace_id}/decks/{deck_id}", json=kwargs)

    def delete_deck(self, workspace_id: str, deck_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/decks/{deck_id}")

    def create_personal_deck(self, name: str, description: str = "", html_content: str = "", deck_type: str = "freeform") -> dict:
        return self._post("/api/v1/decks", json={
            "name": name, "description": description, "html_content": html_content, "deck_type": deck_type,
        })

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

    def update_deck_share(self, deck_id: str, share_id: str, workspace_id: str | None = None, **kwargs) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/decks" if workspace_id else "/api/v1/decks"
        return self._put(f"{base}/{deck_id}/shares/{share_id}", json=kwargs)

    def get_share_analytics(self, deck_id: str, share_id: str, workspace_id: str | None = None) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/decks" if workspace_id else "/api/v1/decks"
        return self._get(f"{base}/{deck_id}/shares/{share_id}/analytics")

    # --- Webhooks ---

    def set_webhook(self, workspace_id: str, url: str, secret: str | None = None) -> dict:
        body: dict = {"url": url}
        if secret:
            body["secret"] = secret
        return self._post(f"/api/v1/workspaces/{workspace_id}/webhooks", json=body)

    # --- Chat Watches ---

    def watch_chat(self, chat_id: str, workspace_id: str | None = None) -> dict:
        params = f"?workspace_id={workspace_id}" if workspace_id else ""
        return self._post(f"/api/v1/personas/me/watches/{chat_id}{params}")

    def unwatch_chat(self, chat_id: str) -> None:
        self._delete(f"/api/v1/personas/me/watches/{chat_id}")

    def list_watches(self) -> list:
        return self._list("/api/v1/personas/me/watches", "watches")

    def get_unread(self) -> dict:
        return self._get("/api/v1/personas/me/unread")

    def mark_read(self, chat_id: str) -> dict:
        return self._post(f"/api/v1/personas/me/watches/{chat_id}/mark-read")

    def search_users(self, query: str) -> list:
        return self._get("/api/v1/dms/users/search", q=query)

    # --- Tables ---

    def create_table(self, workspace_id: str, name: str, description: str = "", columns: list | None = None) -> dict:
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

    def create_personal_table(self, name: str, description: str = "", columns: list | None = None) -> dict:
        body: dict = {"name": name, "description": description, "columns": columns or []}
        return self._post("/api/v1/tables", json=body)

    def list_personal_tables(self) -> list:
        return self._list("/api/v1/tables", "tables")

    def all_tables(self) -> list:
        return self._list("/api/v1/me/tables", "tables")

    def list_table_rows(self, workspace_id: str | None, table_id: str, limit: int = 50, offset: int = 0, sort_by: str = "", sort_order: str = "asc", filters: str = "") -> dict:
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

    def insert_table_rows_batch(self, workspace_id: str | None, table_id: str, rows: list[dict]) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        return self._post(f"{base}/{table_id}/rows/batch", json={"rows": [{"data": r} for r in rows]})

    def update_table_row(self, workspace_id: str | None, table_id: str, row_id: str, data: dict) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        return self._patch(f"{base}/{table_id}/rows/{row_id}", json={"data": data})

    def delete_table_row(self, workspace_id: str | None, table_id: str, row_id: str) -> None:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        self._delete(f"{base}/{table_id}/rows/{row_id}")

    def add_table_column(self, workspace_id: str | None, table_id: str, name: str, col_type: str = "text", options: list | None = None) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        body: dict = {"name": name, "type": col_type}
        if options:
            body["options"] = options
        return self._post(f"{base}/{table_id}/columns", json=body)

    def delete_table_column(self, workspace_id: str | None, table_id: str, column_id: str) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        return self._request("DELETE", f"{base}/{table_id}/columns/{column_id}").json()

    def update_table_column(self, workspace_id: str | None, table_id: str, column_id: str, **kwargs) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        return self._patch(f"{base}/{table_id}/columns/{column_id}", json=kwargs)

    def update_table_rows_batch(self, workspace_id: str | None, table_id: str, updates: list[dict]) -> dict:
        base = f"/api/v1/workspaces/{workspace_id}/tables" if workspace_id else "/api/v1/tables"
        return self._post(f"{base}/{table_id}/rows/batch-update", json={"updates": updates})

    # --- Table Embeddings ---

    def configure_table_embeddings(self, workspace_id: str, table_id: str, enabled: bool = True, columns: list[str] | None = None) -> dict:
        return self._put(f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/embedding", json={"enabled": enabled, "columns": columns or []})

    def backfill_table_embeddings(self, workspace_id: str, table_id: str) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/embedding/backfill")

    def semantic_search_table_rows(self, workspace_id: str, table_id: str, query: str, limit: int = 20) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/rows/semantic-search", "rows", q=query, limit=limit)

    # --- Wiki Features ---

    def get_backlinks(self, workspace_id: str, notebook_id: str, page_id: str) -> list:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}/backlinks")
        return data.get("backlinks", []) if isinstance(data, dict) else data

    def get_outlinks(self, workspace_id: str, notebook_id: str, page_id: str) -> list:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}/outlinks")
        return data.get("outlinks", []) if isinstance(data, dict) else data

    def get_page_graph(self, workspace_id: str, notebook_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/graph")

    def semantic_search_pages(self, workspace_id: str, notebook_id: str, query: str, limit: int = 20) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/semantic-search", "pages", q=query, limit=limit)

    def auto_index_notebook(self, workspace_id: str, notebook_id: str) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/auto-index")

    # --- Files ---

    def upload_file(self, workspace_id: str, name: str, file_path: str, content_type: str = "application/octet-stream") -> dict:
        with open(file_path, "rb") as f:
            resp = self._request("POST", f"/api/v1/workspaces/{workspace_id}/files", files={"file": (name, f, content_type)})
        return resp.json()

    def list_files(self, workspace_id: str) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/files", "files")

    def get_file_url(self, workspace_id: str, file_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/files/{file_id}")

    def delete_file(self, workspace_id: str, file_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/files/{file_id}")

    # --- Documents (RAGFlow) ---

    def upload_document(self, workspace_id: str, name: str, file_path: str) -> dict:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        ct_map = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg",
                  "jpeg": "image/jpeg", "txt": "text/plain", "md": "text/markdown"}
        content_type = ct_map.get(ext, "application/octet-stream")
        with open(file_path, "rb") as f:
            resp = self._request("POST", f"/api/v1/workspaces/{workspace_id}/documents", files={"file": (name, f, content_type)})
        return resp.json()

    def list_documents(self, workspace_id: str, status: str = "") -> list:
        params = {"status": status} if status else {}
        return self._list(f"/api/v1/workspaces/{workspace_id}/documents", "documents", **params)

    def search_documents(self, workspace_id: str, query: str, limit: int = 20) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/documents/search", json={"query": query, "limit": limit})

    def get_document_status(self, workspace_id: str, doc_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/documents/{doc_id}")

    def delete_document(self, workspace_id: str, doc_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/documents/{doc_id}")

    # --- Webhooks ---

    def get_webhook(self, workspace_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/webhooks")

    def update_webhook(self, workspace_id: str, **kwargs) -> dict:
        return self._patch(f"/api/v1/workspaces/{workspace_id}/webhooks", json=kwargs)

    def delete_webhook(self, workspace_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/webhooks")

    # --- Sleep Agent ---

    def get_sleep_config(self) -> dict:
        return self._get("/api/v1/personas/me/sleep/config")

    def configure_sleep_agent(self, **kwargs) -> dict:
        return self._patch("/api/v1/personas/me/sleep/config", json=kwargs)

    def trigger_sleep(self) -> dict:
        return self._post("/api/v1/personas/me/sleep")

    # --- Profile ---

    def update_profile(self, **kwargs) -> dict:
        return self._patch("/api/v1/users/me", json=kwargs)
