"""Apply a saved learned evaluator to new actions without training or calling an LLM."""

import argparse
import json
from pathlib import Path

from rm_worker.artifacts import download_model
from rm_worker.evaluation import action_score_rows


def run(directory: Path) -> None:
    from rm_worker.scoring import RewardModel

    job = json.loads((directory / "job.json").read_text())
    model_dir = download_model(job["reward_model_key"], directory / "checkpoint")
    stats = json.loads((model_dir / "action_reward_stats.json").read_text())
    model = RewardModel(model_dir)
    items = [
        json.loads(line)
        for line in (directory / "action_score_items.jsonl").read_text().splitlines()
    ]
    rows = action_score_rows(items, model.score([item["text"] for item in items]), stats)
    (directory / "action_scores.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (directory / "result.json").write_text(json.dumps({"action_count": len(rows)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", type=Path, required=True)
    run(parser.parse_args().job_dir)
