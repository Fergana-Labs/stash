"""Deploy only after approving the bounded cloud experiment; imports do not load weights."""

from pathlib import Path

import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.14.0", "transformers==5.17.0", "accelerate==1.15.0", "peft==0.21.2")
    .env({"HF_HOME": "/models"})
    .add_local_dir(
        Path(__file__).parent,
        remote_path="/root/scripts/website_taste",
        ignore=["__pycache__", "tests"],
    )
)
app = modal.App("stash-website-taste", image=image)
models = modal.Volume.from_name("stash-website-taste-models", create_if_missing=True)
checkpoints = modal.Volume.from_name("stash-website-taste-checkpoints", create_if_missing=True)


@app.function(
    gpu="L4",
    memory=24576,
    timeout=600,
    max_containers=1,
    scaledown_window=120,
    volumes={"/models": models, "/checkpoints": checkpoints},
)
def generate(model_spec, messages, seed, adapter=None):
    from scripts.website_taste.cloud_worker import generate as worker

    checkpoints.reload()
    return worker(model_spec, messages, seed, adapter)


@app.function(
    gpu="A100-80GB",
    memory=32768,
    timeout=45 * 60,
    max_containers=1,
    volumes={"/models": models, "/checkpoints": checkpoints},
)
def train(model_spec, pairs, config, run_id):
    from scripts.website_taste.cloud_worker import train_dpo

    result = train_dpo(model_spec, pairs, config, run_id)
    checkpoints.commit()
    return result


class RemoteGenerator:
    def __init__(self, spec):
        self.spec = spec
        self.fn = modal.Function.from_name("stash-website-taste", "generate")

    def __call__(self, messages, *, seed, adapter=None):
        return self.fn.remote(self.spec, messages, seed, adapter)
