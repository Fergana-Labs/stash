"""Local upload health tracking for agent hooks.

The server cannot report hook failures when the hook cannot reach the server,
so each plugin writes a small local status file next to its event queue.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

STATUS_FILENAME = "upload_status.json"
QUEUE_FILENAME = "event_queue.jsonl"


def status_path(data_dir: Path) -> Path:
    return data_dir / STATUS_FILENAME


def queue_path(data_dir: Path) -> Path:
    return data_dir / QUEUE_FILENAME


def _now() -> float:
    return time.time()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def _error_text(error: BaseException | str) -> str:
    text = str(error).strip()
    if not text:
        text = type(error).__name__ if isinstance(error, BaseException) else "Upload failed"
    return text[:500]


def _queue_count(data_dir: Path) -> int:
    path = queue_path(data_dir)
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    except OSError:
        return 0


def record_upload_success(data_dir: Path | None, operation: str) -> None:
    if data_dir is None:
        return
    path = status_path(data_dir)
    data = _read_json(path)
    data.update(
        {
            "version": 1,
            "last_attempt_at": data.get("last_attempt_at") or _now(),
            "last_success_at": _now(),
            "last_success_operation": operation,
            "consecutive_failures": 0,
        }
    )
    data.pop("last_error", None)
    try:
        _write_json(path, data)
    except OSError:
        pass


def record_upload_failure(
    data_dir: Path | None,
    operation: str,
    error: BaseException | str,
) -> None:
    if data_dir is None:
        return
    path = status_path(data_dir)
    data = _read_json(path)
    failures = int(data.get("consecutive_failures") or 0) + 1
    now = _now()
    data.update(
        {
            "version": 1,
            "last_attempt_at": now,
            "last_failure_at": now,
            "last_failure_operation": operation,
            "last_error": _error_text(error),
            "consecutive_failures": failures,
        }
    )
    try:
        _write_json(path, data)
    except OSError:
        pass


def record_upload_attempt(data_dir: Path | None, operation: str) -> None:
    if data_dir is None:
        return
    path = status_path(data_dir)
    data = _read_json(path)
    data.update(
        {
            "version": 1,
            "last_attempt_at": _now(),
            "last_attempt_operation": operation,
        }
    )
    try:
        _write_json(path, data)
    except OSError:
        pass


def read_upload_status(data_dir: Path) -> dict[str, Any]:
    data = _read_json(status_path(data_dir))
    data["queued_events"] = _queue_count(data_dir)

    last_success = float(data.get("last_success_at") or 0)
    last_failure = float(data.get("last_failure_at") or 0)
    failures = int(data.get("consecutive_failures") or 0)
    queued = int(data.get("queued_events") or 0)

    if queued or (failures and last_failure >= last_success):
        data["health"] = "failing"
    elif last_success:
        data["health"] = "ok"
    else:
        data["health"] = "unknown"

    return data
