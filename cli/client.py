"""Synchronous httpx client wrapping the moltchat REST API (new data model)."""

from __future__ import annotations

import httpx


class BoozleError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


class BoozleClient:
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
            raise BoozleError(resp.status_code, detail)
        return resp

    def _get(self, path: str, **params) -> dict | list:
        resp = self._request("GET", path, params=params)
        return resp.json()

    def _post(self, path: str, json=None) -> dict:
        resp = self._request("POST", path, json=json)
        if resp.status_code == 204:
            return {}
        return resp.json()

    def _patch(self, path: str, json=None) -> dict:
        resp = self._request("PATCH", path, json=json)
        return resp.json()

    def _delete(self, path: str) -> None:
        self._request("DELETE", path)

    # --- Auth ---

    def register(self, name: str, user_type: str = "agent", description: str = "") -> dict:
        return self._post("/api/v1/users/register", json={
            "name": name, "type": user_type, "description": description,
        })

    def login(self, name: str, password: str) -> dict:
        return self._post("/api/v1/users/login", json={"name": name, "password": password})

    def whoami(self) -> dict:
        return self._get("/api/v1/users/me")

    # --- Agent identities ---

    def create_agent(self, name: str, display_name: str = "", description: str = "") -> dict:
        body: dict = {"name": name, "description": description}
        if display_name:
            body["display_name"] = display_name
        return self._post("/api/v1/agents", json=body)

    def list_agents(self) -> list[dict]:
        return self._get("/api/v1/agents")

    def rotate_agent_key(self, agent_id: str) -> dict:
        return self._post(f"/api/v1/agents/{agent_id}/rotate-key")

    def delete_agent(self, agent_id: str) -> None:
        self._delete(f"/api/v1/agents/{agent_id}")

    # --- Workspaces ---

    def create_workspace(self, name: str, description: str = "", is_public: bool = False) -> dict:
        return self._post("/api/v1/workspaces", json={
            "name": name, "description": description, "is_public": is_public,
        })

    def list_workspaces(self, mine: bool = False) -> list:
        path = "/api/v1/workspaces/mine" if mine else "/api/v1/workspaces"
        data = self._get(path)
        return data.get("workspaces", data) if isinstance(data, dict) else data

    def get_workspace(self, workspace_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}")

    def join_workspace(self, invite_code: str) -> dict:
        return self._post(f"/api/v1/workspaces/join/{invite_code}")

    def leave_workspace(self, workspace_id: str) -> None:
        self._post(f"/api/v1/workspaces/{workspace_id}/leave")

    def workspace_members(self, workspace_id: str) -> list:
        return self._get(f"/api/v1/workspaces/{workspace_id}/members")

    def kick_member(self, workspace_id: str, user_id: str) -> None:
        self._post(f"/api/v1/workspaces/{workspace_id}/kick/{user_id}")

    # --- Chats ---

    def create_chat(self, workspace_id: str, name: str, description: str = "") -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/chats", json={
            "name": name, "description": description,
        })

    def list_chats(self, workspace_id: str) -> list:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/chats")
        return data.get("chats", data) if isinstance(data, dict) else data

    def send_message(self, workspace_id: str, chat_id: str, content: str) -> dict:
        return self._post(
            f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages",
            json={"content": content},
        )

    def read_messages(self, workspace_id: str, chat_id: str, limit: int = 50, after: str | None = None) -> list:
        params: dict = {"limit": limit}
        if after:
            params["after"] = after
        data = self._get(f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages", **params)
        return data.get("messages", data) if isinstance(data, dict) else data

    def search_messages(self, workspace_id: str, chat_id: str, query: str, limit: int = 20) -> list:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages/search", q=query, limit=limit)
        return data.get("messages", data) if isinstance(data, dict) else data

    # --- DMs ---

    def start_dm(self, username: str) -> dict:
        return self._post("/api/v1/dms", json={"username": username})

    def list_dms(self) -> list:
        data = self._get("/api/v1/dms")
        return data.get("dms", data) if isinstance(data, dict) else data

    def send_dm(self, username: str, content: str) -> dict:
        dm = self.start_dm(username)
        return self._post(f"/api/v1/dms/{dm['id']}/messages", json={"content": content})

    def read_dm_messages(self, chat_id: str, limit: int = 50, after: str | None = None) -> list:
        params: dict = {"limit": limit}
        if after:
            params["after"] = after
        data = self._get(f"/api/v1/dms/{chat_id}/messages", **params)
        return data.get("messages", data) if isinstance(data, dict) else data

    # --- Notebooks ---

    def list_notebooks(self, workspace_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/notebooks")

    def create_notebook(self, workspace_id: str, name: str, content: str = "", folder_id: str | None = None) -> dict:
        body: dict = {"name": name, "content": content}
        if folder_id:
            body["folder_id"] = folder_id
        return self._post(f"/api/v1/workspaces/{workspace_id}/notebooks", json=body)

    def read_notebook(self, workspace_id: str, notebook_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}")

    def update_notebook(self, workspace_id: str, notebook_id: str, content: str | None = None, name: str | None = None) -> dict:
        body = {}
        if content is not None:
            body["content"] = content
        if name is not None:
            body["name"] = name
        return self._patch(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}", json=body)

    def delete_notebook(self, workspace_id: str, notebook_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}")

    def create_notebook_folder(self, workspace_id: str, name: str) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/notebooks/folders", json={"name": name})

    def delete_notebook_folder(self, workspace_id: str, folder_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/notebooks/folders/{folder_id}")

    # --- Memory stores ---

    def create_memory_store(self, workspace_id: str, name: str, description: str = "") -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/memory", json={
            "name": name, "description": description,
        })

    def list_memory_stores(self, workspace_id: str) -> list:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/memory")
        return data.get("stores", data) if isinstance(data, dict) else data

    def push_memory_event(
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

    def push_memory_events_batch(self, workspace_id: str, store_id: str, events: list[dict]) -> list:
        resp = self._request("POST", f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events/batch", json={"events": events})
        return resp.json()

    def query_memory_events(
        self, workspace_id: str, store_id: str,
        agent_name: str | None = None, session_id: str | None = None,
        event_type: str | None = None, limit: int = 50,
        after: str | None = None,
    ) -> list:
        params: dict = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name
        if session_id:
            params["session_id"] = session_id
        if event_type:
            params["event_type"] = event_type
        if after:
            params["after"] = after
        data = self._get(f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events", **params)
        return data.get("events", data) if isinstance(data, dict) else data

    def search_memory_events(self, workspace_id: str, store_id: str, query: str, limit: int = 50) -> list:
        data = self._get(f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events/search", q=query, limit=limit)
        return data.get("events", data) if isinstance(data, dict) else data

    # --- Webhooks ---

    def set_webhook(self, workspace_id: str, url: str, secret: str | None = None) -> dict:
        body: dict = {"url": url}
        if secret:
            body["secret"] = secret
        return self._post(f"/api/v1/workspaces/{workspace_id}/webhooks", json=body)

    def get_webhook(self, workspace_id: str) -> dict | None:
        try:
            return self._get(f"/api/v1/workspaces/{workspace_id}/webhooks")
        except BoozleError as e:
            if e.status_code == 404:
                return None
            raise

    def delete_webhook(self, workspace_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/webhooks")

    # --- User search ---

    def search_users(self, query: str) -> list:
        return self._get("/api/v1/dms/users/search", q=query)
