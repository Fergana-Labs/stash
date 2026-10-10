"""Score at most two candidates with a saved checkpoint. Never trains a model."""

import argparse
import json
from pathlib import Path

from rm_worker.artifacts import download_model
from rm_worker.context import render_action_input


def candidate_texts(data: dict, input_version: int, rubric: list[str]) -> list[str]:
    # A saved pair is replayed byte for byte, including each side's original context.
    if "texts" in data:
        return data["texts"]
    if input_version not in (1, 2, 3):
        raise ValueError("This checkpoint's input format is not supported by the playground")
    texts = []
    for response in data["responses"]:
        steps = []
        if data.get("instructions"):
            steps.append({"role": "system", "content": data["instructions"]})
        steps.extend(
            [
                {"role": "user", "content": data["prompt"]},
                {"role": "assistant", "content": response},
            ]
        )
        texts.append(
            render_action_input(steps, rubric)
            if input_version == 3
            else "\n\n".join(
                f"{s['role']}: {s['content']}"
                for s in steps
                if input_version == 2 or s["role"] != "system"
            )
        )
    return texts


def run(directory: Path) -> None:
    from rm_worker.scoring import RewardModel

    job = json.loads((directory / "job.json").read_text())
    checkpoint = download_model(job["reward_model_key"], directory / "checkpoint")
    model = RewardModel(checkpoint)
    texts = candidate_texts(job["input"], model.input_version, model.rubric)
    if not 1 <= len(texts) <= 2:
        raise ValueError("Expected one or two candidates")
    scores = model.score(texts)
    (directory / "result.json").write_text(json.dumps({"scores": scores}, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", type=Path, required=True)
    run(parser.parse_args().job_dir)
