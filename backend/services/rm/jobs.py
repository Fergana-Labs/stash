"""Run reward-model training and GEPA jobs through the rm_worker subprocess.

The backend never imports torch. A job is a directory under RM_ARTIFACT_DIR
(contract in docs/reward-models/DESIGN.md, "Job directory contract"): the
backend writes the inputs, runs `python -m rm_worker.<module> --job-dir <dir>`
with RM_WORKER_PYTHON, and reads result.json / scores.jsonl back.
"""

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
from uuid import UUID

from rm_worker.release_gate import check_partition

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
    config = model.get("training_config")

    pairs = (
        []
        if config
        else await datasets.build_pairs(owner_user_id, model["trace_ids"], model["max_pairs"])
    )
    kwargs = {"training_config": config} if config else {}
    inferred_pairs, findings = await feedback.build_feedback_pairs(
        owner_user_id, model["trace_ids"], model["max_pairs"], **kwargs
    )
    pairs.extend(inferred_pairs)
    pairs = pairs[: model["max_pairs"]]
    if config:
        for pair in pairs:
            pair["task_group"] = config["task_groups"][pair["trace_id"]]
            pair["partition"] = (
                "eval" if pair["task_group"] in config["evaluation_groups"] else "train"
            )
            pair["example_id"] = hashlib.sha256(
                (pair["chosen"] + pair["rejected"]).encode()
            ).hexdigest()
    included = {
        (pair["trace_id"], pair["evidence"]["step_index"])
        for pair in pairs
        if pair.get("source") == "feedback_revision" and pair.get("partition") != "eval"
    }
    for finding in findings:
        finding["included_in_training"] = (
            finding["trace_id"],
            finding["step_index"],
        ) in included and len(pairs) >= datasets.MIN_PAIRS
        if config:
            finding["included_in_evaluation"] = any(
                p["partition"] == "eval"
                and p["trace_id"] == finding["trace_id"]
                and p["evidence"]["step_index"] == finding["step_index"]
                for p in pairs
            )
    await pool.execute(
        "UPDATE rm_reward_models SET num_pairs = $2, training_pairs = $3, feedback = $4 WHERE id = $1",
        model_id,
        len(pairs),
        pairs,
        findings,
    )
    datasets.check_enough_pairs(pairs)
    if config:
        check_partition(pairs)

    directory = job_dir(model_id)
    directory.mkdir(parents=True, exist_ok=True)
    job = {
        "kind": "train",
        "base_model": model["base_model"],
        "epochs": model["epochs"],
        "compute": model["compute"],
        "artifact_key": f"reward-models/{owner_user_id}/{model_id}.tar.gz",
    }
    if config:
        job.update(input_version=3, fixed_split=True, rubric=config["rubric"])
    (directory / "job.json").write_text(json.dumps(job))
    _write_jsonl(directory / "pairs.jsonl", pairs)
    _write_jsonl(
        directory / "score_items.jsonl", [] if config else await datasets.score_items(owner_user_id)
    )
    ids = None
    if config:
        # Initial training scores the sampled actions from these tasks. Further
        # traces are scored explicitly via the existing score endpoint.
        targets = {(f["trace_id"], f["step_index"]) for f in findings}
        rows = await pool.fetch(
            "SELECT id, trace_id, idx FROM rm_trace_steps WHERE trace_id = ANY($1::uuid[])",
            model["trace_ids"],
        )
        ids = {str(r["id"]) for r in rows if (str(r["trace_id"]), r["idx"]) in targets}
    action_items = await datasets.action_score_items(
        owner_user_id,
        input_version=3 if config else 1,
        rubric=config["rubric"] if config else (),
        trace_ids=model["trace_ids"] if config else None,
        step_ids=ids,
    )
    _write_jsonl(directory / "action_score_items.jsonl", action_items)

    module = "rm_worker.modal_runner" if model["compute"] == "modal" else "rm_worker.train"
    await run_worker(module, directory)

    result = json.loads((directory / "result.json").read_text())
    scores = _read_jsonl(directory / "scores.jsonl")
    action_scores = _read_jsonl(directory / "action_scores.jsonl")
    validate_action_scores(
        action_items if result["metrics"].get("action_scoring_version") else [], action_scores
    )
    # Scores, metrics and the succeeded status land together: a model is either
    # fully succeeded or not at all.
    async with pool.acquire() as conn, conn.transaction():
        await store_action_scores(conn, owner_user_id, model_id, action_scores)
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


def validate_action_scores(items: list[dict], scores: list[dict]) -> None:
    expected = {(item["trace_id"], item["step_id"]) for item in items}
    actual = [(row["trace_id"], row["step_id"]) for row in scores]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("Worker did not return exactly the requested action scores")
    if any(
        not math.isfinite(row["score"])
        or not math.isfinite(row["credit"])
        or not -1 <= row["credit"] <= 1
        for row in scores
    ):
        raise ValueError("Worker returned an invalid action score")


async def store_action_scores(
    conn, owner_user_id: UUID, model_id: UUID, scores: list[dict]
) -> None:
    # Step UUIDs change on re-import: stale results can never attach to replacement steps.
    await conn.executemany(
        """
        INSERT INTO rm_action_scores (reward_model_id, step_id, score, credit)
        SELECT m.id, s.id, $4, $5 FROM rm_trace_steps s
        JOIN rm_traces t ON t.id = s.trace_id
        JOIN rm_reward_models m ON m.id = $1 AND (m.owner_user_id = t.owner_user_id
            OR EXISTS (SELECT 1 FROM rm_evaluator_releases r WHERE r.reward_model_id = m.id))
        WHERE s.id = $2 AND t.id = $3 AND t.owner_user_id = $6 AND s.role = 'assistant'
        ON CONFLICT (reward_model_id, step_id)
        DO UPDATE SET score = EXCLUDED.score, credit = EXCLUDED.credit, created_at = now()
        """,
        [
            (
                model_id,
                UUID(row["step_id"]),
                UUID(row["trace_id"]),
                row["score"],
                row["credit"],
                owner_user_id,
            )
            for row in scores
        ],
    )


async def run_scoring(run_id: UUID) -> None:
    pool = get_pool()
    run = await pool.fetchrow(
        """
        SELECT r.*, m.artifact_key, m.compute, m.metrics, m.training_config FROM rm_scoring_runs r
        JOIN rm_reward_models m ON m.id = r.reward_model_id AND (m.owner_user_id = r.owner_user_id
            OR EXISTS (SELECT 1 FROM rm_evaluator_releases er WHERE er.reward_model_id = m.id))
        WHERE r.id = $1 AND m.status = 'succeeded'
        """,
        run_id,
    )
    if run is None or run["artifact_key"] is None:
        raise ValueError("Reward model is unavailable")
    items = await datasets.action_score_items(
        run["owner_user_id"],
        run["trace_id"],
        input_version=(run["metrics"] or {}).get("input_version", 1),
        rubric=(run.get("training_config") or {}).get("rubric", ()),
    )
    if not items:
        raise ValueError("Trace has no assistant actions to score")
    directory = job_dir(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(
        json.dumps({"kind": "score", "reward_model_key": run["artifact_key"]})
    )
    _write_jsonl(directory / "action_score_items.jsonl", items)
    module = "rm_worker.modal_runner" if run["compute"] == "modal" else "rm_worker.score_run"
    await run_worker(module, directory)
    scores = _read_jsonl(directory / "action_scores.jsonl")
    validate_action_scores(items, scores)
    async with pool.acquire() as conn, conn.transaction():
        # Ingestion locks the trace row while replacing its steps. Lock it through publication.
        await conn.fetchrow(
            "SELECT id FROM rm_traces WHERE id = $1 FOR NO KEY UPDATE", run["trace_id"]
        )
        current = await conn.fetch(
            "SELECT id FROM rm_trace_steps WHERE trace_id = $1", run["trace_id"]
        )
        if not {UUID(item["step_id"]) for item in items} <= {s["id"] for s in current}:
            raise ValueError("Trace changed while scoring; score it again")
        await store_action_scores(conn, run["owner_user_id"], run["reward_model_id"], scores)
        await conn.execute(
            "UPDATE rm_scoring_runs SET status = 'succeeded', finished_at = now() WHERE id = $1",
            run_id,
        )
        await conn.execute(
            """DELETE FROM rm_auto_scores q USING rm_traces t, rm_evaluator_registry er
            WHERE q.trace_id = $1 AND t.id = q.trace_id AND t.updated_at = $2 AND er.model_id = $3""",
            run["trace_id"],
            run["trace_updated_at"],
            run["reward_model_id"],
        )


async def run_gepa(run_id: UUID) -> None:
    pool = get_pool()
    run = await pool.fetchrow("SELECT * FROM rm_gepa_runs WHERE id = $1", run_id)

    # The skill learns from the same traces its reward model was trained on.
    model = await pool.fetchrow(
        "SELECT trace_ids, artifact_key, compute, training_pairs, training_config FROM rm_reward_models WHERE id = $1",
        run["reward_model_id"],
    )
    trace_ids = model["trace_ids"]
    config = model.get("training_config")
    if config:
        trace_ids = [
            tid
            for tid in trace_ids
            if config["task_groups"][str(tid)] not in config["evaluation_groups"]
        ]
    if model["artifact_key"] is None:
        raise ValueError("Reward model has no stored checkpoint")
    examples = await datasets.gepa_examples(run["owner_user_id"], trace_ids)
    for example in examples:
        for pair in model["training_pairs"]:
            if (
                pair.get("trace_id") == example["trace_id"]
                and pair.get("source") == "feedback_revision"
                and pair.get("partition") != "eval"
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
