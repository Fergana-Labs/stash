"""Run reward-model training and GEPA jobs through the rm_worker subprocess.

The backend never imports torch. A job is a directory under RM_ARTIFACT_DIR
(contract in docs/reward-models/DESIGN.md, "Job directory contract"): the
backend writes the inputs, runs `python -m rm_worker.<module> --job-dir <dir>`
with RM_WORKER_PYTHON, and reads result.json / scores.jsonl back.
"""

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from ...database import get_pool
from . import datasets, feedback

REPO_ROOT = Path(__file__).resolve().parents[3]
LOG_TAIL_CHARS = 2000


class WorkerFailed(RuntimeError):
    """The worker exited non-zero; the message is the tail of worker.log."""


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; it is required to run reward model jobs")
    return value


def job_dir(job_id: UUID) -> Path:
    return Path(required_env("RM_ARTIFACT_DIR")) / str(job_id)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def run_worker(module: str, directory: Path) -> None:
    python = required_env("RM_WORKER_PYTHON")
    log_path = directory / "worker.log"
    with log_path.open("w") as log:
        process = await asyncio.create_subprocess_exec(
            python,
            "-m",
            module,
            "--job-dir",
            str(directory),
            cwd=REPO_ROOT,
            stdout=log,
            stderr=asyncio.subprocess.STDOUT,
        )
        returncode = await process.wait()
    if returncode != 0:
        raise WorkerFailed(log_path.read_text()[-LOG_TAIL_CHARS:])


async def run_training(model_id: UUID) -> None:
    pool = get_pool()
    model = await pool.fetchrow("SELECT * FROM rm_reward_models WHERE id = $1", model_id)
    owner_user_id = model["owner_user_id"]

    pairs = await datasets.build_pairs(owner_user_id, model["trace_ids"], model["max_pairs"])
    inferred_pairs, findings = await feedback.build_feedback_pairs(
        owner_user_id, model["trace_ids"], model["max_pairs"]
    )
    pairs.extend(inferred_pairs)
    pairs = pairs[: model["max_pairs"]]
    included = {
        (pair["trace_id"], pair["evidence"]["step_index"])
        for pair in pairs
        if pair.get("source") == "feedback_revision"
    }
    for finding in findings:
        finding["included_in_training"] = (
            finding["trace_id"],
            finding["step_index"],
        ) in included and len(pairs) >= datasets.MIN_PAIRS
    await pool.execute(
        "UPDATE rm_reward_models SET num_pairs = $2, training_pairs = $3, feedback = $4 WHERE id = $1",
        model_id,
        len(pairs),
        pairs,
        findings,
    )
    datasets.check_enough_pairs(pairs)

    directory = job_dir(model_id)
    directory.mkdir(parents=True, exist_ok=True)
    job = {
        "kind": "train",
        "base_model": model["base_model"],
        "epochs": model["epochs"],
        "compute": model["compute"],
        "artifact_key": f"reward-models/{owner_user_id}/{model_id}.tar.gz",
    }
    (directory / "job.json").write_text(json.dumps(job))
    _write_jsonl(directory / "pairs.jsonl", pairs)
    _write_jsonl(directory / "score_items.jsonl", await datasets.score_items(owner_user_id))

    module = "rm_worker.modal_runner" if model["compute"] == "modal" else "rm_worker.train"
    await run_worker(module, directory)

    result = json.loads((directory / "result.json").read_text())
    scores = _read_jsonl(directory / "scores.jsonl")
    # Scores, metrics and the succeeded status land together: a model is either
    # fully succeeded or not at all.
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
            UPDATE rm_reward_models
            SET metrics = $2, artifact_key = $3, status = 'succeeded', finished_at = now()
            WHERE id = $1
            """,
            model_id,
            result["metrics"],
            job["artifact_key"],
        )
        await conn.execute("DELETE FROM rm_trace_scores WHERE reward_model_id = $1", model_id)
        # A trace deleted while the job ran has nothing left to attach a score to.
        await conn.executemany(
            """
            INSERT INTO rm_trace_scores (reward_model_id, trace_id, score)
            SELECT $1, t.id, $3 FROM rm_traces t WHERE t.id = $2 AND t.owner_user_id = $4
            """,
            [
                (model_id, UUID(row["trace_id"]), float(row["score"]), owner_user_id)
                for row in scores
            ],
        )


async def run_gepa(run_id: UUID) -> None:
    pool = get_pool()
    run = await pool.fetchrow("SELECT * FROM rm_gepa_runs WHERE id = $1", run_id)

    # The skill learns from the same traces its reward model was trained on.
    model = await pool.fetchrow(
        "SELECT trace_ids, artifact_key, compute, training_pairs FROM rm_reward_models WHERE id = $1",
        run["reward_model_id"],
    )
    trace_ids = model["trace_ids"]
    if model["artifact_key"] is None:
        raise ValueError("Reward model has no stored checkpoint")
    examples = await datasets.gepa_examples(run["owner_user_id"], trace_ids)
    for example in examples:
        for pair in model["training_pairs"]:
            if (
                pair.get("trace_id") == example["trace_id"]
                and pair.get("source") == "feedback_revision"
            ):
                evidence = pair["evidence"]
                source = "AI judgment" if evidence["source"] == "ai_judgment" else "User feedback"
                example["feedback"].append(
                    f"{source}: {evidence['evidence_quote']} — {evidence['reason']}"
                )
    if not examples:
        raise ValueError("need at least one selected trace with a user turn")

    directory = job_dir(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    job = {
        "kind": "gepa",
        "reward_model_key": model["artifact_key"],
        "task_model": run["task_model"],
        "task_api_base": run["task_api_base"],
        "reflection_model": run["reflection_model"],
        "max_metric_calls": run["max_metric_calls"],
    }
    (directory / "job.json").write_text(json.dumps(job))
    _write_jsonl(directory / "gepa_examples.jsonl", examples)

    module = "rm_worker.modal_runner" if model["compute"] == "modal" else "rm_worker.gepa_run"
    await run_worker(module, directory)

    result = json.loads((directory / "result.json").read_text())
    await pool.execute(
        """
        UPDATE rm_gepa_runs
        SET skill_name = $7, skill_description = $8,
            best_skill = $2, best_score = $3, seed_skill = $4, seed_score = $5,
            candidates = $6, status = 'succeeded', finished_at = now()
        WHERE id = $1
        """,
        run_id,
        result["best_skill"],
        result["best_score"],
        result["seed_skill"],
        result["seed_score"],
        result["candidates"],
        result["skill_name"],
        result["skill_description"],
    )
