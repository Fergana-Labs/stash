"""Apply a saved learned evaluator to new actions without training or calling an LLM."""

import argparse
import json
from pathlib import Path

from rm_worker.artifacts import download_model
from rm_worker.evaluation import action_score_rows
from rm_worker.progress import Reporter


def run(directory: Path) -> None:
    progress = Reporter()
    progress.update("downloading")
    from rm_worker.scoring import RewardModel

    job = json.loads((directory / "job.json").read_text())
    model_dir = download_model(job["reward_model_key"], directory / "checkpoint")
    progress.update("loading")
    model = RewardModel(model_dir)
    items = [
        json.loads(line)
        for line in (directory / "action_score_items.jsonl").read_text().splitlines()
    ]
    trace_path = directory / "score_items.jsonl"
    trace_items = (
        [json.loads(line) for line in trace_path.read_text().splitlines()]
        if trace_path.exists()
        else []
    )
    total = len(items) + len(trace_items)
    progress.update("scoring", 0, total)
    rows = []
    if items:
        stats = json.loads((model_dir / "action_reward_stats.json").read_text())
        rows = action_score_rows(
            items,
            model.score(
                [item["text"] for item in items],
                on_progress=lambda completed: progress.update("scoring", completed, total),
            ),
            stats,
        )
    (directory / "action_scores.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    trace_scores = (
        model.score(
            [item["text"] for item in trace_items],
            on_progress=lambda completed: progress.update("scoring", len(items) + completed, total),
        )
        if trace_items
        else []
    )
    progress.update("saving")
    (directory / "scores.jsonl").write_text(
        "".join(
            json.dumps({"trace_id": item["trace_id"], "score": score}) + "\n"
            for item, score in zip(trace_items, trace_scores, strict=True)
        )
    )
    (directory / "result.json").write_text(json.dumps({"action_count": len(rows)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", type=Path, required=True)
    run(parser.parse_args().job_dir)
