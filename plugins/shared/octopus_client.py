"""Lightweight Octopus HTTP client for plugin hooks. Extracted from cli/client.py.

Events now live directly on a workspace. No intermediate "store" abstraction.

Failed event pushes (network blip, backend cold start, slow GC) get appended to
`<data_dir>/event_queue.jsonl`. The next successful push drains a batch of the
backlog so the queue clears during normal traffic instead of needing a separate
flush daemon.
"""

from __future__ import annotations

import fcntl
import json
import time
from pathlib import Path

import httpx

QUEUE_FILENAME = "event_queue.jsonl"
QUEUE_MAX_ENTRIES = 1000  # cap so a long backend outage doesn't fill the disk
DRAIN_BATCH = 50          # how many backlog rows to flush per successful push


class OctopusError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


class OctopusClient:
    def __init__(self, base_url: str, api_key: str = "", data_dir: str | Path | None = None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._data_dir = Path(data_dir) if data_dir else None
        self._http = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(2.0, connect=1.0),
        )

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

    # --- Events ---
    #
    # workspace_id=None targets the personal store (/api/v1/memory/events).
    # A non-empty workspace_id scopes to that workspace.

    def _events_path(self, workspace_id: str | None) -> str:
        if workspace_id:
            return f"/api/v1/workspaces/{workspace_id}/memory/events"
        return "/api/v1/memory/events"

    def push_event(
        self, workspace_id: str | None,
        agent_name: str, event_type: str, content: str,
        session_id: str | None = None, tool_name: str | None = None,
        metadata: dict | None = None, client: str | None = None,
    ) -> dict:
        body: dict = {"agent_name": agent_name, "event_type": event_type, "content": content}
        if session_id:
            body["session_id"] = session_id
        if tool_name:
            body["tool_name"] = tool_name
        merged_meta = dict(metadata or {})
        if client:
            merged_meta["client"] = client
        if merged_meta:
            body["metadata"] = merged_meta

        path = self._events_path(workspace_id)
        try:
            result = self._post(path, json=body)
        except Exception:
            self._enqueue(path, body)
            raise
        # Backend reachable — try to flush some of the backlog while we're here.
        self._drain_queue()
        return result

    # --- Failed-event queue ---

    def _queue_path(self) -> Path | None:
        if not self._data_dir:
            return None
        return self._data_dir / QUEUE_FILENAME

    def _enqueue(self, path: str, body: dict) -> None:
        qp = self._queue_path()
        if not qp:
            return
        try:
            qp.parent.mkdir(parents=True, exist_ok=True)
            entry = json.dumps({"path": path, "body": body, "ts": time.time()})
            with open(qp, "a") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(entry + "\n")
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            # Cheap upper bound: trim only when grossly oversized.
            self._maybe_trim_queue(qp)
        except Exception:
            pass

    def _maybe_trim_queue(self, qp: Path) -> None:
        try:
            with open(qp, "r+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    lines = f.read().splitlines()
                    if len(lines) <= QUEUE_MAX_ENTRIES:
                        return
                    # Keep the most recent QUEUE_MAX_ENTRIES; oldest are sacrificed.
                    keep = lines[-QUEUE_MAX_ENTRIES:]
                    f.seek(0)
                    f.truncate()
                    f.write("\n".join(keep) + ("\n" if keep else ""))
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass

    def _drain_queue(self) -> None:
        qp = self._queue_path()
        if not qp or not qp.exists():
            return
        try:
            with open(qp, "r+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    lines = f.read().splitlines()
                    if not lines:
                        return
                    remaining: list[str] = []
                    sent = 0
                    for line in lines:
                        if sent >= DRAIN_BATCH:
                            remaining.append(line)
                            continue
                        try:
                            entry = json.loads(line)
                            self._post(entry["path"], json=entry["body"])
                            sent += 1
                        except Exception:
                            # Backend still unhappy. Stop now; keep this and the rest.
                            remaining.append(line)
                            # Don't try further entries — likely all will fail.
                            sent = DRAIN_BATCH
                    f.seek(0)
                    f.truncate()
                    if remaining:
                        f.write("\n".join(remaining) + "\n")
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass

    def query_events(
        self, workspace_id: str | None,
        agent_name: str | None = None, event_type: str | None = None,
        session_id: str | None = None,
        limit: int = 50, after: str | None = None,
    ) -> list:
        params: dict = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        if session_id:
            params["session_id"] = session_id
        if after:
            params["after"] = after
        return self._list(self._events_path(workspace_id), "events", **params)

    def search_events(self, workspace_id: str | None, query: str, limit: int = 50) -> list:
        return self._list(
            f"{self._events_path(workspace_id)}/search",
            "events", q=query, limit=limit,
        )

    # --- Cross-workspace aggregate (optional) ---

    def list_all_history_events(
        self, agent_name: str | None = None, event_type: str | None = None,
        limit: int = 50,
    ) -> list:
        params: dict = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name
        if event_type:
            params["event_type"] = event_type
        return self._list("/api/v1/me/history-events", "events", **params)
