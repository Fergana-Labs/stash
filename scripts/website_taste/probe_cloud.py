"""Separate cloud app for frozen activations and the tiny learned readout."""

from pathlib import Path

import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.6.0",
        "torchvision==0.21.0",
        "transformers==4.57.6",
        "accelerate==1.12.0",
        "pillow==11.3.0",
        "numpy==2.2.6",
        "scipy==1.15.3",
    )
    .env({"HF_HOME": "/models", "TOKENIZERS_PARALLELISM": "false"})
    .add_local_dir(
        Path(__file__).parent,
        remote_path="/root/scripts/website_taste",
        ignore=["__pycache__", "tests"],
    )
)
app = modal.App("stash-website-taste-probe", image=image)
models = modal.Volume.from_name("stash-website-taste-probe-models", create_if_missing=True)


@app.function(
    gpu="L4",
    memory=16384,
    timeout=900,
    max_containers=1,
    scaledown_window=30,
    volumes={"/models": models},
)
def extract(payloads, spec):
    from scripts.website_taste.activation_worker import extract as worker

    result = worker(payloads, spec)
    models.commit()
    return result


@app.function(memory=1024, timeout=60, max_containers=1, scaledown_window=2)
def fit(rows):
    from scripts.website_taste.activation_worker import fit_probe

    return fit_probe(rows)
