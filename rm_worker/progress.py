"""Small structured progress events carried by local and Modal worker logs."""

import json
import math
import re
import time
from datetime import UTC, datetime

PREFIX = "STASH_TRAINING_PROGRESS "
STAGES = {"preparing", "starting", "loading", "training", "evaluating", "scoring", "uploading"}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class Reporter:
    def __init__(self):
        self.stage = None
        self.started = 0.0
        self.last_sent = 0.0

    def update(self, stage: str, completed: int = 0, total: int = 0):
        now = time.monotonic()
        changed = stage != self.stage
        if changed:
            self.stage, self.started = stage, now
        if not changed and completed != total and now - self.last_sent < 2:
            return
        self.last_sent = now
        print(
            PREFIX
            + json.dumps(
                {
                    "stage": stage,
                    "completed": completed,
                    "total": total,
                    "elapsed_seconds": round(now - self.started, 2),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            flush=True,
        )


def parse_event(line: str) -> dict | None:
    """Ignore ordinary logs, malformed events, and terminal decorations."""
    line = ANSI.sub("", line)
    if PREFIX not in line:
        return None
    try:
        event, _ = json.JSONDecoder().raw_decode(line.split(PREFIX, 1)[1])
        if event["stage"] not in STAGES:
            return None
        completed, total, elapsed = event["completed"], event["total"], event["elapsed_seconds"]
        if (
            type(completed) is not int
            or type(total) is not int
            or not 0 <= completed <= total
            or not math.isfinite(elapsed)
            or elapsed < 0
        ):
            return None
        if datetime.fromisoformat(event["updated_at"]).tzinfo is None:
            return None
        return {
            key: event[key]
            for key in ("stage", "completed", "total", "elapsed_seconds", "updated_at")
        }
    except (ValueError, KeyError, TypeError):
        return None
