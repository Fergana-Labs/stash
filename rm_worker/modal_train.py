"""Run rm_worker.train on a Modal A10G and write its outputs into the local job directory.

    python -m rm_worker.modal_train --job-dir DIR

The job directory ends up exactly as local training leaves it: model/,
scores.jsonl and result.json.
"""

import argparse
import io
import tarfile
import tempfile
from pathlib import Path

import modal

WORKER_DIR = Path(__file__).parent
INPUT_FILES = ["job.json", "pairs.jsonl", "score_items.jsonl"]
OUTPUT_FILES = ["model", "scores.jsonl", "result.json"]

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(WORKER_DIR / "requirements.txt"))
    .add_local_python_source("rm_worker", ignore=[".venv", ".scratch", "**/__pycache__"])
)
app = modal.App("stash-rm-train", image=image)


@app.function(gpu="A10G", timeout=6 * 60 * 60)
def train_remote(inputs: dict[str, bytes]) -> bytes:
    from rm_worker.train import train

    job_dir = Path(tempfile.mkdtemp())
    for name, data in inputs.items():
        (job_dir / name).write_bytes(data)
    train(job_dir)

    # Uncompressed: the weights are most of the bytes and do not compress.
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name in OUTPUT_FILES:
            tar.add(job_dir / name, arcname=name)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a reward model on a Modal GPU.")
    parser.add_argument("--job-dir", type=Path, required=True)
    job_dir = parser.parse_args().job_dir

    inputs = {name: (job_dir / name).read_bytes() for name in INPUT_FILES}
    with modal.enable_output(), app.run():
        outputs = train_remote.remote(inputs)

    with tarfile.open(fileobj=io.BytesIO(outputs), mode="r") as tar:
        tar.extractall(job_dir, filter="data")
    print(f"wrote {', '.join(OUTPUT_FILES)} to {job_dir}", flush=True)


if __name__ == "__main__":
    main()
