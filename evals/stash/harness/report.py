"""
Aggregate trial metrics + judge outputs into a SQLite DB and markdown summary.

Usage:
    # After trials + judging finish for a run:
    python -m harness.report --run-id 20260416T210000Z
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = EVAL_ROOT / "runs"
DB_PATH = EVAL_ROOT / "runs.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS trials (
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    arm TEXT NOT NULL,
    trial INTEGER NOT NULL,
    start_ts TEXT,
    end_ts TEXT,
    pass INTEGER,
    overall_score REAL,
    tokens_input INTEGER,
    tokens_output INTEGER,
    tokens_cache_read INTEGER,
    tokens_cache_create INTEGER,
    total_tool_calls INTEGER,
    wall_clock_s REAL,
    time_to_first_edit_s REAL,
    stash_first INTEGER,
    rediscovery_count INTEGER,
    workspace_id TEXT,
    raw_metrics TEXT,
    raw_judge TEXT,
    PRIMARY KEY (run_id, task_id, arm, trial)
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def load_trial(run_id: str, task_id: str, arm: str, trial: int) -> dict | None:
    trial_dir = RUNS_DIR / run_id / f"arm_{arm}" / f"trial_{trial}"
    metrics_path = trial_dir / "metrics.json"
    judge_path = trial_dir / "judge.json"
    if not metrics_path.exists():
        return None
    metrics = json.loads(metrics_path.read_text())
    judge_result = json.loads(judge_path.read_text()) if judge_path.exists() else {}
    return {
        "metrics": metrics,
        "judge": judge_result,
        "task_id": task_id,
        "run_id": run_id,
        "arm": arm,
        "trial": trial,
    }


def upsert(conn: sqlite3.Connection, row: dict) -> None:
    m = row["metrics"]
    j = row["judge"]
    conn.execute(
        """
        INSERT OR REPLACE INTO trials
        (run_id, task_id, arm, trial, start_ts, end_ts, pass, overall_score,
         tokens_input, tokens_output, tokens_cache_read, tokens_cache_create,
         total_tool_calls, wall_clock_s, time_to_first_edit_s, stash_first,
         rediscovery_count, workspace_id, raw_metrics, raw_judge)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["run_id"],
            row["task_id"],
            row["arm"],
            row["trial"],
            m.get("start_ts"),
            m.get("end_ts"),
            1 if j.get("pass") else 0,
            j.get("overall_score"),
            m["tokens"]["input"],
            m["tokens"]["output"],
            m["tokens"]["cache_read"],
            m["tokens"]["cache_create"],
            m.get("total_tool_calls"),
            m.get("wall_clock_s"),
            m.get("time_to_first_edit_s"),
            1 if m.get("stash_first") else 0,
            m.get("rediscovery_count"),
            m.get("workspace_id"),
            json.dumps(m, default=str),
            json.dumps(j, default=str),
        ),
    )
    conn.commit()


def ingest_run(run_id: str) -> sqlite3.Connection:
    """Walk runs/<run_id>/arm_*/trial_* and ingest everything."""
    conn = connect()
    run_dir = RUNS_DIR / run_id
    for arm_dir in sorted(run_dir.glob("arm_*")):
        arm = arm_dir.name.split("_")[1]
        for trial_dir in sorted(arm_dir.glob("trial_*")):
            trial = int(trial_dir.name.split("_")[1])
            metrics_path = trial_dir / "metrics.json"
            if not metrics_path.exists():
                continue
            task_id = json.loads(metrics_path.read_text()).get("task_id", "unknown")
            row = load_trial(run_id, task_id, arm, trial)
            if row:
                upsert(conn, row)
    return conn


def summarize(conn: sqlite3.Connection, run_id: str) -> str:
    cur = conn.execute("SELECT * FROM trials WHERE run_id = ?", (run_id,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    if not rows:
        return f"# Run {run_id}\n\nNo trials found.\n"

    by_arm: dict[str, list[dict]] = {"a": [], "b": []}
    for r in rows:
        by_arm.setdefault(r["arm"], []).append(r)

    lines = [f"# Run {run_id}", ""]
    lines.append("## Per-arm medians")
    lines.append("")
    lines.append("| metric | arm a | arm b | Δ (b−a) |")
    lines.append("|---|---|---|---|")

    numeric = [
        ("pass rate", "pass", lambda xs: sum(xs) / len(xs) if xs else 0),
        ("overall_score (median)", "overall_score", _median),
        ("tokens_input (median)", "tokens_input", _median),
        ("tokens_output (median)", "tokens_output", _median),
        ("tool_calls (median)", "total_tool_calls", _median),
        ("wall_clock_s (median)", "wall_clock_s", _median),
        ("time_to_first_edit_s (median)", "time_to_first_edit_s", _median),
        ("rediscovery_count (median)", "rediscovery_count", _median),
        ("stash_first rate", "stash_first", lambda xs: sum(xs) / len(xs) if xs else 0),
    ]
    for label, col, agg in numeric:
        a = agg([r[col] for r in by_arm.get("a", []) if r[col] is not None])
        b = agg([r[col] for r in by_arm.get("b", []) if r[col] is not None])
        delta = (b - a) if (a is not None and b is not None) else None
        lines.append(f"| {label} | {_fmt(a)} | {_fmt(b)} | {_fmt(delta)} |")

    lines.append("")
    lines.append("## Per-trial")
    lines.append("")
    lines.append("| arm | trial | pass | score | tokens_out | tools | wall_s | ttfe_s | stash_first | redisc |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['arm']} | {r['trial']} | {r['pass']} | {_fmt(r['overall_score'])} "
            f"| {r['tokens_output']} | {r['total_tool_calls']} "
            f"| {_fmt(r['wall_clock_s'])} | {_fmt(r['time_to_first_edit_s'])} "
            f"| {r['stash_first']} | {r['rediscovery_count']} |"
        )
    return "\n".join(lines) + "\n"


def _median(xs: list) -> float | None:
    if not xs:
        return None
    return statistics.median(xs)


def _fmt(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.2f}"
    return str(x)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    conn = ingest_run(args.run_id)
    md = summarize(conn, args.run_id)
    out_path = RUNS_DIR / args.run_id / "summary.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(md)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
