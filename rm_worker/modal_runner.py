"""Run training and skill generation on an isolated Modal GPU."""

import argparse
import json
import os
import tempfile
from pathlib import Path

import modal

WORKER_DIR = Path(__file__).parent
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(WORKER_DIR / "requirements.txt"))
    .add_local_python_source("rm_worker", ignore=[".venv", ".scratch", "**/__pycache__"])
)
app = modal.App("stash-reward-models", image=image)
SECRET_KEYS = (
    "S3_ENDPOINT",
    "S3_BUCKET",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_REGION",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)


def run_job(inputs: dict[str, bytes]) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        for name, data in inputs.items():
            if name not in ("job.json", "pairs.jsonl", "score_items.jsonl", "gepa_examples.jsonl"):
                raise ValueError(f"Unexpected job input: {name}")
            (directory / name).write_bytes(data)
        kind = json.loads(inputs["job.json"])["kind"]
        if kind == "train":
            from rm_worker.train import train

            train(directory)
            outputs = ["result.json", "scores.jsonl"]
        elif kind == "gepa":
            from rm_worker.gepa_run import run

            run(directory)
            outputs = ["result.json"]
        else:
            raise ValueError(f"Unknown reward job kind: {kind}")
        return {name: (directory / name).read_bytes() for name in outputs}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", type=Path, required=True)
    directory = parser.parse_args().job_dir
    job = json.loads((directory / "job.json").read_text())
    names = (
        ["job.json", "pairs.jsonl", "score_items.jsonl"]
        if job["kind"] == "train"
        else ["job.json", "gepa_examples.jsonl"]
    )
    inputs = {name: (directory / name).read_bytes() for name in names}
    secret = modal.Secret.from_dict(
        {key: os.environ[key] for key in SECRET_KEYS if key in os.environ}
    )
    remote = app.function(gpu="A10G", timeout=20 * 60, secrets=[secret])(run_job)
    with modal.enable_output(), app.run():
        outputs = remote.remote(inputs)
    for name, data in outputs.items():
        (directory / name).write_bytes(data)


if __name__ == "__main__":
    main()
