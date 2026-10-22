"""Serve read-only Codex history requests using the existing Stash login."""

from __future__ import annotations

import time
from uuid import uuid4

import httpx

from stashai.local_history import CodexHistory

from .client import StashClient, StashError

PREFIX = "/api/v1/model-wizard/history/local"


def serve(client: StashClient) -> None:
    device = str(uuid4())
    history = CodexHistory()
    connected = False
    while True:
        try:
            response = client._post(PREFIX + "/poll", json={"device_id": device})
            if not connected:
                print(
                    "Local Codex history connected. Only requested excerpts are sent; no sessions are imported. Ctrl-C disconnects.",
                    flush=True,
                )
                connected = True
            request = response.get("request")
            if request:
                try:
                    result = history.run(request["operation"], request["args"])
                except (OSError, ValueError) as exc:
                    result = {"error": str(exc)[:200]}
                try:
                    client._post(
                        PREFIX + "/results/" + request["id"],
                        json={"device_id": device, "result": result},
                    )
                except StashError as exc:
                    if exc.status_code != 404:  # A timed-out request was already removed.
                        raise
            else:
                time.sleep(1)
        except StashError as exc:
            if exc.status_code in (401, 403, 404, 409):
                raise
            time.sleep(3)
        except httpx.HTTPError:
            time.sleep(3)
