"""Evaluate a saved checkpoint on a frozen preference benchmark."""

import argparse
import json
from pathlib import Path

from rm_worker.artifacts import download_model


def run(directory: Path) -> None:
    from rm_worker.scoring import RewardModel

    job = json.loads((directory / "job.json").read_text())
    model_dir = download_model(job["reward_model_key"], directory / "checkpoint")
    model = RewardModel(model_dir)
    pairs = [
        json.loads(line) for line in (directory / "evaluation_pairs.jsonl").read_text().splitlines()
    ]
    scores = model.score([p[k] for p in pairs for k in ("chosen", "rejected")])
    if len(scores) != 2 * len(pairs):
        raise ValueError("Invalid number of evaluation rewards")
    import math

    if not all(math.isfinite(s) for s in scores):
        raise ValueError("Non-finite evaluation reward")
    rows = [
        {"example_id": p["example_id"], "correct": scores[2 * i] > scores[2 * i + 1]}
        for i, p in enumerate(pairs)
    ]
    (directory / "evaluation.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", type=Path, required=True)
    run(parser.parse_args().job_dir)
