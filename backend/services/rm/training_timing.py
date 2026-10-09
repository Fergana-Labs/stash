"""Timing estimates from comparable successful runs or observed training batches.

Queue latency is unknown. A live batch estimate covers training only; evaluation,
scoring and upload are not silently assumed to take zero time.
"""

from datetime import UTC, datetime, timedelta
from statistics import median


def estimate(model, history, *, now=None) -> dict | None:
    if model["status"] not in ("queued", "running"):
        return None
    now = now or datetime.now(UTC)
    config = model.get("training_config") or {}
    samples = []
    for old in history:
        old_config = old.get("training_config") or {}
        if (
            old["status"] != "succeeded"
            or old["base_model"] != model["base_model"]
            or old["compute"] != model["compute"]
            or old["epochs"] != model["epochs"]
            or old_config.get("input_version", 1) != config.get("input_version", 1)
            or old_config.get("annotation_source") != config.get("annotation_source")
            or not old["started_at"]
            or not old["finished_at"]
            or old["finished_at"] < now - timedelta(days=30)
        ):
            continue
        # Avoid extrapolating from a substantially different dataset size.
        key = "num_pairs" if model.get("num_pairs") else "trace_count"
        size = model.get(key)
        old_size = (
            old.get(key)
            if key == "num_pairs"
            else old.get("trace_count", len(old.get("trace_ids", [])))
        )
        if not size or not old_size or not 0.5 <= size / old_size <= 2:
            continue
        seconds = (old["finished_at"] - old["started_at"]).total_seconds()
        if seconds > 0:
            samples.append(seconds)
        if len(samples) == 20:
            break
    if samples:
        typical = median(samples)
        # Broad observed range, widened for sparse history; never an exact deadline.
        low, high = min(min(samples), typical * 0.7), max(max(samples), typical * 1.3)
        elapsed = max(0, (now - model["started_at"]).total_seconds()) if model["started_at"] else 0
        return {
            "basis": "history",
            "scope": "job",
            "sample_count": len(samples),
            "lower_seconds": max(0, round(low - elapsed)),
            "upper_seconds": max(0, round(high - elapsed)),
            "overdue": elapsed >= high,
            "excludes_queue": model["status"] == "queued",
        }
    progress = model.get("progress") or {}
    if model["status"] == "running" and progress.get("stage") == "training":
        completed, total, elapsed = (
            progress.get(key, 0) for key in ("completed", "total", "elapsed_seconds")
        )
        updated = datetime.fromisoformat(progress["updated_at"])
        age = max(0, (now - updated).total_seconds())
        if completed >= 2 and completed < total and elapsed > 0 and age < 60:
            remaining = elapsed / completed * (total - completed)
            return {
                "basis": "batches",
                "scope": "training",
                "sample_count": completed,
                "lower_seconds": max(0, round(remaining * 0.7 - age)),
                "upper_seconds": max(0, round(remaining * 1.3 - age)),
                "overdue": age >= remaining * 1.3,
                "excludes_queue": False,
            }
    return None
