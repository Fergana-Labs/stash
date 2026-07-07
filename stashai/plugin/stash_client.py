"""Lightweight Stash HTTP client for plugin hooks. Extracted from cli/client.py.

Sessions and events stream to the calling user's scope (`/api/v1/me/...`). No
scope abstraction.

Failed event pushes (network blip, backend cold start, slow GC) get appended to
`<data_dir>/event_queue.jsonl`. The next successful push drains a batch of the
backlog so the queue clears during normal traffic instead of needing a separate
flush daemon.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from filelock import FileLock

from stashai.plugin.upload_status import (
    record_upload_attempt,
    record_upload_failure,
    record_upload_success,
)

QUEUE_FILENAME = "event_queue.jsonl"
QUEUE_MAX_ENTRIES = 1000  # cap so a long backend outage doesn't fill the disk
DRAIN_BATCH = 50  # how many backlog rows to flush per successful push


class StashError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


def _is_permanent_rejection(e: Exception) -> bool:
    """A 4xx the backend will never accept no matter when we retry.

    Auth (401/403) heals with a re-signin and 408/429 heal on their own, so
    those stay queued. Every other 4xx (404 dead route, 422 bad body, ...) is
    rejected forever — retrying it just wedges the queue.
    """
    if not isinstance(e, StashError):
        return False
    if e.status_code in (401, 403, 408, 429):
        return False
    return 400 <= e.status_code < 500


class StashClient:
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
            raise StashError(resp.status_code, detail)
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

    # --- Events ---

    _EVENTS_PATH = "/api/v1/me/sessions/events"

    def push_event(
        self,
        agent_name: str,
        event_type: str,
        content: str,
        session_id: str,
        tool_name: str | None = None,
        metadata: dict | None = None,
        client: str | None = None,
        session_folder_id: str | None = None,
    ) -> dict:
        body: dict = {
            "agent_name": agent_name,
            "event_type": event_type,
            "content": content,
            "session_id": session_id,
        }
        # Pin streamed on every event so the session lands in the right folder
        # no matter which event creates the row (agents without a session-start
        # hook create it from the first event, not from create_session).
        if session_folder_id:
            body["session_folder_id"] = session_folder_id
        if tool_name:
            body["tool_name"] = tool_name
        merged_meta = dict(metadata or {})
        if client:
            merged_meta["client"] = client
        if merged_meta:
            body["metadata"] = merged_meta

        path = self._EVENTS_PATH
        record_upload_attempt(self._data_dir, "event")
        try:
            result = self._post(path, json=body)
        except Exception as e:
            self._enqueue(path, body)
            record_upload_failure(self._data_dir, "event", e)
            raise
        # The live push landed — that's a success regardless of how the
        # backlog drain below fares (drain failures are recorded on their own
        # as "event_queue", and health stays failing while anything is queued).
        record_upload_success(self._data_dir, "event")
        # Backend reachable — try to flush some of the backlog while we're here.
        self._drain_queue()
        return result

    # --- Failed-event queue ---

    def _queue_path(self) -> Path | None:
        if not self._data_dir:
            return None
        return self._data_dir / QUEUE_FILENAME

    def _queue_lock(self, qp: Path) -> FileLock:
        # Cross-platform advisory lock on a sidecar file so concurrent hook
        # processes don't corrupt the queue. fcntl is Unix-only; FileLock works
        # on Windows too. Time out rather than hang a hook on a stuck lock.
        return FileLock(str(qp) + ".lock", timeout=10)

    def _enqueue(self, path: str, body: dict) -> None:
        qp = self._queue_path()
        if not qp:
            return
        try:
            qp.parent.mkdir(parents=True, exist_ok=True)
            entry = json.dumps({"path": path, "body": body, "ts": time.time()})
            with self._queue_lock(qp), open(qp, "a") as f:
                f.write(entry + "\n")
            # Cheap upper bound: trim only when grossly oversized.
            self._maybe_trim_queue(qp)
        except Exception:
            pass

    def _maybe_trim_queue(self, qp: Path) -> None:
        try:
            with self._queue_lock(qp), open(qp, "r+") as f:
                lines = f.read().splitlines()
                if len(lines) <= QUEUE_MAX_ENTRIES:
                    return
                # Keep the most recent QUEUE_MAX_ENTRIES; oldest are sacrificed.
                keep = lines[-QUEUE_MAX_ENTRIES:]
                f.seek(0)
                f.truncate()
                f.write("\n".join(keep) + ("\n" if keep else ""))
        except Exception:
            pass

    def _drain_queue(self) -> bool:
        qp = self._queue_path()
        if not qp or not qp.exists():
            return True
        drained = True
        try:
            with self._queue_lock(qp), open(qp, "r+") as f:
                lines = f.read().splitlines()
                if not lines:
                    return True
                remaining: list[str] = []
                sent = 0
                for line in lines:
                    if sent >= DRAIN_BATCH:
                        remaining.append(line)
                        continue
                    try:
                        entry = json.loads(line)
                        path, body = entry["path"], entry["body"]
                    except (ValueError, KeyError):
                        # Corrupt line — it can never send, so drop it rather
                        # than wedge the queue behind it forever.
                        continue
                    try:
                        self._post(path, json=body)
                        sent += 1
                    except Exception as e:
                        record_upload_failure(self._data_dir, "event_queue", e)
                        if _is_permanent_rejection(e):
                            # The backend will never accept this entry (e.g. a
                            # 404 for a route that no longer exists). Drop it
                            # and keep draining the rest.
                            sent += 1
                            continue
                        # Retryable (network, 5xx, auth) — keep this and the
                        # rest for a later drain; further entries would likely
                        # fail the same way.
                        remaining.append(line)
                        drained = False
                        sent = DRAIN_BATCH
                f.seek(0)
                f.truncate()
                if remaining:
                    f.write("\n".join(remaining) + "\n")
        except Exception:
            return False
        return drained

    def query_events(
        self,
        agent_name: str | None = None,
        event_type: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        after: str | None = None,
        order: str | None = None,
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
        if order:
            params["order"] = order
        return self._list(self._EVENTS_PATH, "events", **params)

    def search_events(self, query: str, limit: int = 50) -> list:
        return self._list(
            f"{self._EVENTS_PATH}/search",
            "events",
            q=query,
            limit=limit,
        )

    # --- Transcript upload: gzip the .jsonl client-side (compresses 5-10x),
    # then upload. Backend stores the gzipped blob as-is. Default client
    # timeout is 2s — way too short for a big file — so we override per-
    # request.
    def upload_transcript(
        self,
        session_id: str,
        transcript_path: Path,
        agent_name: str,
        cwd: str | None = None,
        session_folder_id: str | None = None,
    ) -> dict:
        import gzip

        raw = transcript_path.read_bytes()
        body = gzip.compress(raw)
        name = transcript_path.name
        if not name.endswith(".gz"):
            name = name + ".gz"

        data = {"session_id": session_id, "agent_name": agent_name, "cwd": cwd or ""}
        # Omit when unset so the backend routes the session to the Default folder.
        if session_folder_id:
            data["session_folder_id"] = session_folder_id

        record_upload_attempt(self._data_dir, "transcript")
        try:
            resp = self._http.request(
                "POST",
                "/api/v1/me/transcripts",
                headers=self._headers(),
                data=data,
                files={"file": (name, body, "application/gzip")},
                timeout=httpx.Timeout(60.0, connect=5.0),
            )
            if not resp.is_success:
                raise StashError(resp.status_code, resp.text)
        except Exception as e:
            record_upload_failure(self._data_dir, "transcript", e)
            raise
        record_upload_success(self._data_dir, "transcript")
        return resp.json()

    # --- Sessions ---

    def create_session(
        self,
        session_id: str,
        agent_name: str,
        cwd: str | None = None,
        files_touched: list[str] | None = None,
        session_folder_id: str | None = None,
    ) -> dict:
        body = {
            "session_id": session_id,
            "agent_name": agent_name,
            "cwd": cwd or "",
            "files_touched": files_touched or [],
        }
        # Omit when unset so the backend routes the session to the Default folder.
        if session_folder_id:
            body["session_folder_id"] = session_folder_id
        return self._post("/api/v1/me/sessions", json=body)

    def upload_session_artifact(
        self,
        session_row_id: str,
        file_path: str,
        content: bytes,
    ) -> dict:
        """Upload a file the agent touched during a session."""
        record_upload_attempt(self._data_dir, "artifact")
        try:
            resp = self._http.request(
                "POST",
                f"/api/v1/me/sessions/{session_row_id}/artifacts",
                headers=self._headers(),
                data={"file_path": file_path},
                files={"file": (file_path.split("/")[-1], content, "application/octet-stream")},
                timeout=httpx.Timeout(30.0, connect=5.0),
            )
            if not resp.is_success:
                raise StashError(resp.status_code, resp.text)
        except Exception as e:
            record_upload_failure(self._data_dir, "artifact", e)
            raise
        record_upload_success(self._data_dir, "artifact")
        return resp.json()

    # --- History aggregate (optional) ---

    def list_all_history_events(
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
        return self._list("/api/v1/me/history-events", "events", **params)
