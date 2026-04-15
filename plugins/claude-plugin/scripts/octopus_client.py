"""Lightweight Octopus HTTP client for plugin hooks. Extracted from cli/client.py."""

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
        self._http = httpx.Client(base_url=self._base_url, timeout=10)

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

    def _list(self, path: str, key: str, **params) -> list:
        data = self._get(path, **params)
        return data.get(key, data) if isinstance(data, dict) else data

    # --- Auth ---

    def whoami(self) -> dict:
        return self._get("/api/v1/users/me")

    # --- Workspaces ---

    def create_workspace(self, name: str, description: str = "", is_public: bool = False) -> dict:
        return self._post("/api/v1/workspaces", json={
            "name": name, "description": description, "is_public": is_public,
        })

    def list_workspaces(self, mine: bool = False) -> list:
        path = "/api/v1/workspaces/mine" if mine else "/api/v1/workspaces"
        return self._list(path, "workspaces")

    # --- History ---

    def push_event(
        self, workspace_id: str, agent_name: str, event_type: str, content: str,
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
        return self._post(f"/api/v1/workspaces/{workspace_id}/memory/events", json=body)

    def query_events(
        self, workspace_id: str,
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
        return self._list(f"/api/v1/workspaces/{workspace_id}/memory/events", "events", **params)

    def search_events(self, workspace_id: str, query: str, limit: int = 50) -> list:
        return self._list(f"/api/v1/workspaces/{workspace_id}/memory/events/search", "events", q=query, limit=limit)

