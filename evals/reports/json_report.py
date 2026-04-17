"""JSON report writer — persists results for CI comparison and trending."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evals.harness import SuiteResult

_OUTPUT_DIR = Path(__file__).parent / "output"


def write(suite_results: "list[SuiteResult]", path: Path | None = None) -> Path:
    """Write results to a timestamped JSON file. Returns the written path."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = path or (_OUTPUT_DIR / f"eval_{ts}.json")

    payload = {
        "timestamp": ts,
        "passed": all(s.passed for s in suite_results),
        "suites": [_serialise_suite(s) for s in suite_results],
    }

    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    return out_path


def _serialise_suite(s: "SuiteResult") -> dict:
    return {
        "name": s.suite,
        "passed": s.passed,
        "pass_rate": s.pass_rate,
        "duration_s": round(s.duration_s, 3),
        "aggregate": {k: round(v, 4) for k, v in s.aggregate.items()},
        "scenarios": [
            {
                "id": r.scenario_id,
                "description": r.description,
                "passed": r.passed,
                "metrics": {k: round(v, 4) for k, v in r.metrics.items()},
                "error": r.error,
            }
            for r in s.results
        ],
    }


def compare(baseline_path: Path, current_path: Path) -> dict:
    """Compare two result files and return a diff summary."""
    with open(baseline_path) as f:
        baseline = json.load(f)
    with open(current_path) as f:
        current = json.load(f)

    diffs = []
    for cur_suite in current["suites"]:
        name = cur_suite["name"]
        base_suite = next((s for s in baseline["suites"] if s["name"] == name), None)
        if base_suite is None:
            diffs.append({"suite": name, "status": "new"})
            continue

        for metric, cur_val in cur_suite["aggregate"].items():
            base_val = base_suite["aggregate"].get(metric)
            if base_val is None:
                continue
            delta = cur_val - base_val
            if abs(delta) > 0.01:
                diffs.append({
                    "suite": name,
                    "metric": metric,
                    "baseline": round(base_val, 4),
                    "current": round(cur_val, 4),
                    "delta": round(delta, 4),
                    "direction": "improved" if delta > 0 else "regressed",
                })

    return {
        "baseline": baseline_path.name,
        "current": current_path.name,
        "overall_passed": current["passed"],
        "regressions": [d for d in diffs if d.get("direction") == "regressed"],
        "improvements": [d for d in diffs if d.get("direction") == "improved"],
    }
