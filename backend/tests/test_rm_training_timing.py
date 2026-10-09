from datetime import UTC, datetime, timedelta

import pytest

from backend.services.rm.training_timing import estimate

NOW = datetime(2026, 10, 9, 6, tzinfo=UTC)
MODEL = {
    "status": "queued",
    "base_model": "small",
    "compute": "modal",
    "epochs": 1,
    "trace_count": 2,
    "num_pairs": None,
    "started_at": None,
    "training_config": None,
}
PAST = {
    **MODEL,
    "status": "succeeded",
    "started_at": NOW - timedelta(minutes=20),
    "finished_at": NOW - timedelta(minutes=10),
    "num_pairs": 100,
}


def test_queue_duration_excludes_unmeasurable_queue_wait():
    result = estimate(MODEL, [PAST], now=NOW)
    assert result == {
        "basis": "history",
        "scope": "job",
        "sample_count": 1,
        "lower_seconds": 420,
        "upper_seconds": 780,
        "overdue": False,
        "excludes_queue": True,
    }


def test_running_estimate_decreases_and_expires_instead_of_claiming_done():
    running = {**MODEL, "status": "running", "started_at": NOW - timedelta(minutes=5)}
    assert estimate(running, [PAST], now=NOW)["upper_seconds"] == 480
    late = estimate(running, [PAST], now=NOW + timedelta(minutes=20))
    assert late["overdue"] is True
    assert late["upper_seconds"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "failed"},
        {"compute": "local"},
        {"base_model": "large"},
        {"epochs": 10},
        {"trace_count": 50},
        {"training_config": {"input_version": 3}},
        {"training_config": {"annotation_source": "automatic"}},
        {"finished_at": NOW - timedelta(days=31)},
        {"started_at": None},
    ],
)
def test_incomparable_or_invalid_history_has_no_estimate(changes):
    assert estimate(MODEL, [{**PAST, **changes}], now=NOW) is None


def test_known_pair_count_is_more_useful_than_trace_count():
    assert estimate({**MODEL, "num_pairs": 1000}, [PAST], now=NOW) is None
    assert estimate({**MODEL, "num_pairs": 100}, [{**PAST, "trace_count": 99}], now=NOW)


def test_first_run_uses_live_batch_timing_for_training_only():
    model = {
        **MODEL,
        "status": "running",
        "progress": {
            "stage": "training",
            "completed": 10,
            "total": 30,
            "elapsed_seconds": 100,
            "updated_at": NOW.isoformat(),
        },
    }
    result = estimate(model, [], now=NOW)
    assert result["scope"] == "training"
    assert result["upper_seconds"] == 260
    assert result["lower_seconds"] == 140
    assert result["sample_count"] == 10
    assert estimate(model, [], now=NOW + timedelta(seconds=60)) is None
    model["progress"]["completed"] = 1
    assert estimate(model, [], now=NOW) is None
    model["progress"]["completed"] = 30
    assert estimate(model, [], now=NOW) is None
    model["status"] = "failed"
    assert estimate(model, [PAST], now=NOW) is None
