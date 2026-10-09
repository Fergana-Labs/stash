import asyncio
import json
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from backend.services.rm import training_progress
from rm_worker.progress import PREFIX, Reporter, parse_event


def event(**kwargs):
    return {
        "stage": "training",
        "completed": 4,
        "total": 10,
        "elapsed_seconds": 20,
        "updated_at": datetime.now(UTC).isoformat(),
        **kwargs,
    }


def test_log_transport_accepts_decorated_events_and_rejects_invalid_data():
    value = event()
    assert parse_event("\x1b[32mremote: " + PREFIX + json.dumps(value) + "\x1b[0m") == value
    for bad in (
        "ordinary log",
        PREFIX + "{",
        PREFIX + "[]",
        PREFIX + json.dumps(event(completed=99)),
        PREFIX + json.dumps(event(elapsed_seconds=float("nan"))),
        PREFIX + json.dumps(event(updated_at="today")),
    ):
        assert parse_event(bad) is None


def test_reporter_sends_stage_changes_and_final_batch_without_waiting(capsys):
    reporter = Reporter()
    reporter.update("loading")
    reporter.update("training", 0, 10)
    reporter.update("training", 1, 10)  # Throttled.
    reporter.update("training", 10, 10)
    reporter.update("evaluating")
    events = [parse_event(line) for line in capsys.readouterr().out.splitlines()]
    assert [e["stage"] for e in events] == ["loading", "training", "training", "evaluating"]
    assert events[2]["completed"] == 10


async def test_progress_crosses_a_real_subprocess_log_without_ml(tmp_path, monkeypatch):
    save = AsyncMock()
    monkeypatch.setattr(training_progress, "save", save)
    value = event()
    log_path = tmp_path / "worker.log"
    # Split an event across writes, followed by a final event without a newline.
    payload = PREFIX + json.dumps(value)
    code = "import sys,time; sys.stdout.write(sys.argv[1][:20]); sys.stdout.flush(); time.sleep(.05); sys.stdout.write(sys.argv[1][20:]); sys.stdout.flush()"
    with log_path.open("w") as output:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code, payload, stdout=output
        )
        model_id = uuid4()
        assert await training_progress.watch(process, log_path, model_id) == 0
    save.assert_awaited_once_with(model_id, value)


async def test_progress_write_failure_does_not_fail_training(monkeypatch):
    pool = AsyncMock()
    pool.execute.side_effect = RuntimeError("temporary DB error")
    monkeypatch.setattr(training_progress, "get_pool", lambda: pool)
    await training_progress.stage(uuid4(), "preparing")
