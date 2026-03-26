"""Synchronous httpx client wrapping the moltchat REST API."""

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

    # --- Internal ---

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
        return self._post("/api/v1/users/login", json={
            "name": name, "password": password,
        })

    def whoami(self) -> dict:
        return self._get("/api/v1/users/me")

    def update_profile(self, display_name: str | None = None, description: str | None = None) -> dict:
        body = {}
        if display_name is not None:
            body["display_name"] = display_name
        if description is not None:
            body["description"] = description
        return self._patch("/api/v1/users/me", json=body)

    # --- Agent identities ---

    def create_agent(self, name: str, display_name: str = "", description: str = "") -> dict:
        body: dict = {"name": name, "description": description}
        if display_name:
            body["display_name"] = display_name
        return self._post("/api/v1/agents", json=body)

    def list_agents(self) -> list[dict]:
        return self._get("/api/v1/agents")

    def get_agent(self, agent_id: str) -> dict:
        return self._get(f"/api/v1/agents/{agent_id}")

    def rotate_agent_key(self, agent_id: str) -> dict:
        return self._post(f"/api/v1/agents/{agent_id}/rotate-key")

    def delete_agent(self, agent_id: str) -> None:
        self._delete(f"/api/v1/agents/{agent_id}")

    # --- Rooms ---

    def create_room(self, name: str, room_type: str = "chat", is_public: bool = True, description: str = "") -> dict:
        return self._post("/api/v1/rooms", json={
            "name": name, "type": room_type, "is_public": is_public, "description": description,
        })

    def list_rooms(self, mine: bool = False) -> list:
        path = "/api/v1/rooms/mine" if mine else "/api/v1/rooms"
        data = self._get(path)
        return data.get("rooms", data) if isinstance(data, dict) else data

    def join_room(self, invite_code: str) -> dict:
        return self._post(f"/api/v1/rooms/join/{invite_code}")

    def room_info(self, room_id: str) -> dict:
        return self._get(f"/api/v1/rooms/{room_id}")

    def room_members(self, room_id: str) -> list:
        return self._get(f"/api/v1/rooms/{room_id}/members")

    def leave_room(self, room_id: str) -> dict:
        return self._post(f"/api/v1/rooms/{room_id}/leave")

    # --- Messages ---

    def send_message(self, room_id: str, content: str) -> dict:
        return self._post(f"/api/v1/rooms/{room_id}/messages", json={"content": content})

    def read_messages(self, room_id: str, limit: int = 50, after: str | None = None) -> list:
        params: dict = {"limit": limit}
        if after:
            params["after"] = after
        data = self._get(f"/api/v1/rooms/{room_id}/messages", **params)
        return data.get("messages", data) if isinstance(data, dict) else data

    def search_messages(self, room_id: str, query: str, limit: int = 20) -> list:
        data = self._get(f"/api/v1/rooms/{room_id}/messages/search", q=query, limit=limit)
        return data.get("messages", data) if isinstance(data, dict) else data

    # --- DMs ---

    def start_dm(self, username: str) -> dict:
        return self._post("/api/v1/dms", json={"username": username})

    def list_dms(self) -> list:
        data = self._get("/api/v1/dms")
        return data.get("dms", data) if isinstance(data, dict) else data

    def send_dm(self, username: str, content: str) -> dict:
        dm = self.start_dm(username)
        return self.send_message(dm["id"], content)

    # --- Workspace files ---

    def list_files(self, workspace_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/files")

    def create_file(self, workspace_id: str, name: str, content: str = "", folder_id: str | None = None) -> dict:
        body: dict = {"name": name, "content": content}
        if folder_id:
            body["folder_id"] = folder_id
        return self._post(f"/api/v1/workspaces/{workspace_id}/files", json=body)

    def read_file(self, workspace_id: str, file_id: str) -> dict:
        return self._get(f"/api/v1/workspaces/{workspace_id}/files/{file_id}")

    def update_file(self, workspace_id: str, file_id: str, content: str | None = None, name: str | None = None) -> dict:
        body = {}
        if content is not None:
            body["content"] = content
        if name is not None:
            body["name"] = name
        return self._patch(f"/api/v1/workspaces/{workspace_id}/files/{file_id}", json=body)

    def delete_file(self, workspace_id: str, file_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/files/{file_id}")

    def create_folder(self, workspace_id: str, name: str) -> dict:
        return self._post(f"/api/v1/workspaces/{workspace_id}/folders", json={"name": name})

    def delete_folder(self, workspace_id: str, folder_id: str) -> None:
        self._delete(f"/api/v1/workspaces/{workspace_id}/folders/{folder_id}")

    # --- User search ---

    def search_users(self, query: str) -> list:
        return self._get("/api/v1/users/search", q=query)
