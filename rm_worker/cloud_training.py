"""Detached personal-model training, including preparation, outside Render.

Only the model ID crosses the dispatch boundary. The cloud job reads its
private inputs and writes results directly, so Render restarts cannot cancel
it or lose the completed checkpoint. No ML package is imported by the caller.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from uuid import UUID

import modal

from rm_worker.modal_runner import SECRET_KEYS

training_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(Path(__file__).parent / "requirements.txt"))
    .pip_install(
        "asyncpg==0.30.0", "pgvector==0.4.2", "python-dotenv", "anthropic>=1.9.0", "cryptography"
    )
    .env({"DB_POOL_MIN": "1", "DB_POOL_MAX": "3"})
    .add_local_python_source(
        "backend",
        "rm_worker",
        ignore=["**/.env*", "**/.venv/**", "**/.secrets/**", "**/__pycache__/**"],
    )
)
TIMEOUT_SECONDS = 40 * 60


async def train(model_id: str) -> None:
    from backend import database
    from backend.services.rm import jobs

    await database.init_pool()
    try:
        model = await database.get_pool().fetchrow(
            "SELECT status, scope FROM rm_reward_models WHERE id=$1", UUID(model_id)
        )
        if model is None or model["status"] != "running" or model["scope"] != "personal":
            return
        previous_env = {
            key: os.environ.get(key)
            for key in ("RM_ARTIFACT_DIR", "RM_WORKER_PYTHON", "RM_TRAINING_ON_CLOUD_GPU")
        }
        with tempfile.TemporaryDirectory() as directory:
            os.environ["RM_ARTIFACT_DIR"] = directory
            os.environ["RM_WORKER_PYTHON"] = sys.executable
            # The subprocess already runs on this cloud GPU; do not launch
            # a second Modal app or depend on a connected local client.
            os.environ["RM_TRAINING_ON_CLOUD_GPU"] = "1"
            try:
                await jobs.run_training(UUID(model_id))
            except (Exception, asyncio.CancelledError) as exc:
                await database.get_pool().execute(
                    """UPDATE rm_reward_models SET status='failed', error=$2, finished_at=now()
                    WHERE id=$1 AND status='running'""",
                    UUID(model_id),
                    str(exc)[-2000:] or "Cloud training was cancelled or timed out",
                )
                raise
            finally:
                for key, value in previous_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
    finally:
        await database.close_db()


def dispatch(model_id: str) -> str:
    app = modal.App("stash-personal-model-training", image=training_image)
    secret = modal.Secret.from_dict(
        {
            key: os.environ[key]
            for key in (*SECRET_KEYS, "DATABASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_FAST_MODEL")
            if key in os.environ
        }
    )
    remote = app.function(gpu="A10G", memory=8192, timeout=TIMEOUT_SECONDS, secrets=[secret])(train)
    with app.run(detach=True):
        call = remote.spawn(model_id)
        return call.object_id
