"""Shared default evaluator, an approved training corpus, and gated releases.

Public callers receive only release summaries and scores on their own traces.
The corpus and candidate controls are exclusively operator endpoints.
"""

import hashlib
import json
from uuid import UUID

from rm_worker.release_gate import DEFAULT_POLICY, check_partition, evaluate_release

from ...database import get_pool
from . import feedback, jobs


class EvaluatorInvalid(ValueError):
    pass


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


async def default_evaluator() -> dict | None:
    row = await get_pool().fetchrow("""
        SELECT m.id, m.name, r.revision, r.updated_at FROM rm_evaluator_registry r
        JOIN rm_reward_models m ON m.id = r.model_id WHERE m.status = 'succeeded'
    """)
    return dict(row) if row else None


async def can_score(owner: UUID, model_id: UUID):
    return await get_pool().fetchrow(
        """
        SELECT * FROM rm_reward_models m WHERE m.id = $1 AND
        (m.owner_user_id = $2 OR EXISTS (SELECT 1 FROM rm_evaluator_releases r WHERE r.reward_model_id = m.id))
    """,
        model_id,
        owner,
    )


async def enqueue_score(
    owner: UUID, trace_id: UUID, model_id: UUID, *, automatic=False
) -> tuple[dict, bool]:
    pool = get_pool()
    run = await pool.fetchrow(
        """
        INSERT INTO rm_scoring_runs(owner_user_id, trace_id, reward_model_id, automatic, trace_updated_at)
        SELECT $1, id, $3, $4, updated_at FROM rm_traces WHERE id = $2 AND owner_user_id = $1
        ON CONFLICT (trace_id, reward_model_id) WHERE status IN ('queued', 'running') DO NOTHING RETURNING *
    """,
        owner,
        trace_id,
        model_id,
        automatic,
    )
    created = run is not None
    if run is None:
        run = await pool.fetchrow(
            "SELECT * FROM rm_scoring_runs WHERE trace_id = $1 AND reward_model_id = $2 ORDER BY created_at DESC LIMIT 1",
            trace_id,
            model_id,
        )
    if run is None:
        raise EvaluatorInvalid("Trace was deleted")
    return dict(run), created


async def set_contribution(owner: UUID, trace_id: UUID, allowed: bool) -> dict | None:
    row = await get_pool().fetchrow(
        """
        UPDATE rm_traces SET shared_training_allowed = $3, learning_revision = learning_revision + 1
        WHERE id = $1 AND owner_user_id = $2 RETURNING id, shared_training_allowed
    """,
        trace_id,
        owner,
        allowed,
    )
    return dict(row) if row else None


async def collect_examples(trace_id: UUID) -> None:
    pool = get_pool()
    claimed = await pool.fetchrow(
        """
        UPDATE rm_example_collection SET status = 'running', started_at = now(), attempts = attempts + 1
        WHERE trace_id = $1 AND status = 'queued' RETURNING *
    """,
        trace_id,
    )
    if claimed is None:
        return
    trace = await pool.fetchrow(
        "SELECT * FROM rm_traces WHERE id = $1 AND shared_training_allowed", trace_id
    )
    if trace is None:
        return
    try:
        pairs, _ = await feedback.build_feedback_pairs(
            trace["owner_user_id"], [trace_id], 200, shared=True
        )
        async with pool.acquire() as conn, conn.transaction():
            current = await conn.fetchrow(
                "SELECT * FROM rm_traces WHERE id = $1 FOR NO KEY UPDATE", trace_id
            )
            if (
                current is None
                or not current["shared_training_allowed"]
                or current["updated_at"] != trace["updated_at"]
                or current["learning_revision"] != trace["learning_revision"]
            ):
                return  # mutation trigger already requeued or revoked the contribution
            metadata = trace["metadata"] or {}
            for pair in pairs:
                provenance = {
                    "source": "independently_reviewed",
                    "evidence": pair["evidence"],
                    "labeler_model": feedback.settings.ANTHROPIC_MODEL,
                    "input_version": 2,
                    "permission": "trace_opt_in",
                    "learning_revision": trace["learning_revision"],
                }
                await insert_example(
                    conn,
                    trace["owner_user_id"],
                    pair,
                    task_group=f"trace:{trace_id}",
                    domain=str(metadata.get("domain", "unspecified")),
                    agent=str(metadata.get("agent", "unspecified")),
                    partition="train",
                    provenance=provenance,
                    trace_id=trace_id,
                )
            await conn.execute(
                "UPDATE rm_example_collection SET status = 'succeeded', error = NULL WHERE trace_id = $1",
                trace_id,
            )
    except Exception as exc:
        # Do not mark a replacement generation failed.
        await pool.execute(
            """UPDATE rm_example_collection c SET status = 'failed', error = $2, due_at = now() + interval '1 minute'
            FROM rm_traces t WHERE c.trace_id = $1 AND t.id = c.trace_id
              AND t.learning_revision = $3 AND t.updated_at = $4""",
            trace_id,
            str(exc)[-1000:],
            trace["learning_revision"],
            trace["updated_at"],
        )
        raise


async def insert_example(
    conn,
    owner: UUID,
    pair: dict,
    *,
    task_group: str,
    domain: str,
    agent: str,
    partition: str,
    provenance: dict,
    trace_id: UUID | None = None,
):
    if (
        not pair["chosen"].strip()
        or not pair["rejected"].strip()
        or pair["chosen"] == pair["rejected"]
    ):
        raise EvaluatorInvalid("A comparison needs distinct nonempty alternatives")
    fingerprint = digest(sorted([pair["chosen"], pair["rejected"]]))
    await conn.execute(
        "INSERT INTO rm_task_partitions(task_group, partition) VALUES ($1,$2) ON CONFLICT DO NOTHING",
        task_group,
        partition,
    )
    assigned = await conn.fetchval(
        "SELECT partition FROM rm_task_partitions WHERE task_group = $1 FOR SHARE", task_group
    )
    if assigned != partition:
        raise EvaluatorInvalid("A task group's training/evaluation partition is permanent")
    if partition == "eval" and provenance.get("source") not in ("human", "verified_outcome"):
        raise EvaluatorInvalid("The benchmark requires human judgments or verified outcomes")
    return await conn.fetchval(
        """
        INSERT INTO rm_training_examples(owner_user_id, trace_id, task_group, domain, agent, partition, pair, provenance, fingerprint)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(fingerprint) DO NOTHING RETURNING id
    """,
        owner,
        trace_id,
        task_group,
        domain,
        agent,
        partition,
        pair,
        provenance,
        fingerprint,
    )


async def corpus_snapshot(conn=None) -> list[dict]:
    rows = await (conn or get_pool()).fetch("""
        SELECT e.* FROM rm_training_examples e LEFT JOIN rm_traces t ON t.id = e.trace_id
        WHERE e.trace_id IS NULL OR t.shared_training_allowed ORDER BY e.id
    """)
    return [
        {
            **r["pair"],
            "example_id": str(r["id"]),
            "partition": r["partition"],
            "task_group": r["task_group"],
            "domain": r["domain"],
            "agent": r["agent"],
            "trace_id": str(r["trace_id"] or r["id"]),
            "granularity": "action",
        }
        for r in rows
    ]


async def check_snapshot_valid(pairs: list[dict]) -> None:
    ids = [UUID(p["example_id"]) for p in pairs]
    valid = await get_pool().fetchval(
        """SELECT count(*) FROM rm_training_examples e
        LEFT JOIN rm_traces t ON t.id = e.trace_id WHERE e.id = ANY($1::uuid[])
        AND (e.trace_id IS NULL OR t.shared_training_allowed)""",
        ids,
    )
    if valid != len(ids):
        raise EvaluatorInvalid(
            "Training contribution changed or was revoked; create a new candidate"
        )


async def create_candidate(owner: UUID, name: str, base_model: str, epochs: int) -> dict:
    # Shared training is always remote; the worker must never default to this laptop.
    pairs = await corpus_snapshot()
    check_partition(pairs)
    if not await get_pool().fetchval("SELECT 1 FROM users WHERE id = $1", owner):
        raise EvaluatorInvalid("Operator owner account does not exist")
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('rm_shared_training'))")
        return await _insert_candidate(conn, owner, name, base_model, epochs, pairs)


async def _insert_candidate(conn, owner, name, base_model, epochs, pairs, automatic_release=False):
    if await conn.fetchval(
        "SELECT 1 FROM rm_reward_models WHERE scope = 'shared' AND status IN ('queued', 'running')"
    ):
        raise EvaluatorInvalid("A shared candidate is already queued or running")
    parent = await conn.fetchval("SELECT model_id FROM rm_evaluator_registry WHERE singleton")
    row = await conn.fetchrow(
        """
        INSERT INTO rm_reward_models(owner_user_id,name,base_model,compute,epochs,max_pairs,trace_ids,scope,parent_model_id,training_pairs,num_pairs,automatic_release)
        VALUES ($1,$2,$3,'modal',$4,$5,'{}','shared',$6,$7,$5,$8) RETURNING id, status, parent_model_id
    """,
        owner,
        name,
        base_model,
        epochs,
        len(pairs),
        parent,
        pairs,
        automatic_release,
    )
    return dict(row)


async def configure_automation(config: dict) -> dict:
    if not await get_pool().fetchval("SELECT 1 FROM users WHERE id = $1", config["owner_user_id"]):
        raise EvaluatorInvalid("Operator owner account does not exist")
    row = await get_pool().fetchrow(
        """
        INSERT INTO rm_evaluator_automation(singleton,enabled,owner_user_id,base_model,epochs,min_new_examples,interval_hours,auto_promote)
        VALUES (true,$1,$2,$3,$4,$5,$6,$7)
        ON CONFLICT(singleton) DO UPDATE SET enabled=$1,owner_user_id=$2,base_model=$3,epochs=$4,
        min_new_examples=$5,interval_hours=$6,auto_promote=$7 RETURNING *
    """,
        *(
            config[k]
            for k in (
                "enabled",
                "owner_user_id",
                "base_model",
                "epochs",
                "min_new_examples",
                "interval_hours",
                "auto_promote",
            )
        ),
    )
    return dict(row)


async def schedule_candidate() -> dict | None:
    # Same lock as manual creation makes simultaneous sweeps and manual requests safe.
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('rm_shared_training'))")
        config = await conn.fetchrow("""SELECT * FROM rm_evaluator_automation WHERE enabled
            AND (last_attempt_at IS NULL OR last_attempt_at < now() - interval_hours * interval '1 hour')
            FOR UPDATE""")
        if not config or await conn.fetchval(
            "SELECT 1 FROM rm_reward_models WHERE scope='shared' AND status IN ('queued','running')"
        ):
            return None
        pairs = await corpus_snapshot(conn)
        new_train = {UUID(p["example_id"]) for p in pairs if p["partition"] == "train"} - set(
            config["last_example_ids"]
        )
        if len(new_train) < config["min_new_examples"]:
            return None
        await conn.execute(
            "UPDATE rm_evaluator_automation SET last_attempt_at=now(), error=NULL WHERE singleton"
        )
        try:
            check_partition(pairs)
            candidate = await _insert_candidate(
                conn,
                config["owner_user_id"],
                "Stash evaluator candidate",
                config["base_model"],
                config["epochs"],
                pairs,
                config["auto_promote"],
            )
        except ValueError as exc:
            await conn.execute(
                "UPDATE rm_evaluator_automation SET error=$1 WHERE singleton", str(exc)
            )
            return None
        await conn.execute(
            "UPDATE rm_evaluator_automation SET last_example_ids=$1 WHERE singleton",
            [UUID(p["example_id"]) for p in pairs],
        )
        return candidate


async def evaluate_checkpoint(directory, model_key: str, pairs: list[dict]) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(
        json.dumps({"kind": "evaluate", "reward_model_key": model_key})
    )
    jobs._write_jsonl(directory / "evaluation_pairs.jsonl", pairs)
    await jobs.run_worker("rm_worker.modal_runner", directory)
    return json.loads((directory / "evaluation.json").read_text())


async def train_candidate(model_id: UUID) -> None:
    pool = get_pool()
    model = await pool.fetchrow(
        "SELECT * FROM rm_reward_models WHERE id = $1 AND scope = 'shared'", model_id
    )
    pairs = model["training_pairs"]
    _, benchmark = check_partition(pairs)
    await check_snapshot_valid(pairs)
    directory = jobs.job_dir(model_id)
    directory.mkdir(parents=True, exist_ok=True)
    parent_key = await pool.fetchval(
        "SELECT artifact_key FROM rm_reward_models WHERE id = $1", model["parent_model_id"]
    )
    key = f"reward-models/shared/{model_id}.tar.gz"
    job = {
        "kind": "train",
        "base_model": model["base_model"],
        "epochs": model["epochs"],
        "compute": "modal",
        "artifact_key": key,
        "fixed_split": True,
        "input_version": 2,
    }
    (directory / "job.json").write_text(json.dumps(job))
    jobs._write_jsonl(directory / "pairs.jsonl", pairs)
    jobs._write_jsonl(directory / "score_items.jsonl", [])
    jobs._write_jsonl(directory / "action_score_items.jsonl", [])
    await jobs.run_worker("rm_worker.modal_runner", directory)
    metrics = json.loads((directory / "result.json").read_text())["metrics"]
    if metrics.get("action_scoring_version") != 1 or metrics.get("input_version") != 2:
        raise EvaluatorInvalid("Candidate checkpoint does not support shared action scoring")
    predictions = await evaluate_checkpoint(directory / "candidate-eval", key, benchmark)
    baseline = (
        await evaluate_checkpoint(directory / "baseline-eval", parent_key, benchmark)
        if parent_key
        else None
    )
    report = evaluate_release(pairs, predictions, baseline)
    report.update(
        {
            "parent_model_id": str(model["parent_model_id"]) if model["parent_model_id"] else None,
            "dataset_hash": digest(pairs),
            "evaluated_example_ids": [p["example_id"] for p in benchmark],
        }
    )
    await check_snapshot_valid(pairs)
    await pool.execute(
        """UPDATE rm_reward_models SET metrics = $2, artifact_key = $3, release_report = $4,
        status = 'succeeded', finished_at = now() WHERE id = $1""",
        model_id,
        metrics,
        key,
        report,
    )
    if (
        model["automatic_release"]
        and report["passed"]
        and await pool.fetchval(
            "SELECT enabled AND auto_promote FROM rm_evaluator_automation WHERE singleton"
        )
    ):
        try:
            await promote(
                model_id,
                "Automatic release: passed the frozen benchmark against the incumbent",
                automatic=True,
            )
        except EvaluatorInvalid as exc:
            # A concurrent rollback or revoked contribution must leave the default unchanged.
            await pool.execute(
                "UPDATE rm_reward_models SET release_report = release_report || $2::jsonb WHERE id=$1",
                model_id,
                {"promotion_error": str(exc)},
            )


async def promote(model_id: UUID, reason: str, *, rollback=False, automatic=False) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        if automatic:
            config = await conn.fetchrow(
                "SELECT enabled, auto_promote FROM rm_evaluator_automation WHERE singleton FOR SHARE"
            )
            if not config or not config["enabled"] or not config["auto_promote"]:
                raise EvaluatorInvalid("Automatic releases have been disabled")
        await conn.execute(
            "INSERT INTO rm_evaluator_registry(singleton) VALUES (true) ON CONFLICT DO NOTHING"
        )
        registry = await conn.fetchrow(
            "SELECT * FROM rm_evaluator_registry WHERE singleton FOR UPDATE"
        )
        model = await conn.fetchrow(
            "SELECT * FROM rm_reward_models WHERE id = $1 AND scope = 'shared'", model_id
        )
        if model is None or model["status"] != "succeeded" or not model["artifact_key"]:
            raise EvaluatorInvalid("Shared candidate is not ready")
        if registry["model_id"] == model_id:
            return {"model_id": model_id, "revision": registry["revision"]}
        if rollback:
            if not await conn.fetchval(
                "SELECT 1 FROM rm_evaluator_releases WHERE reward_model_id = $1", model_id
            ):
                raise EvaluatorInvalid("Rollback requires a previously released evaluator")
        else:
            report = model["release_report"] or {}
            if (
                not report.get("passed")
                or report.get("dataset_hash") != digest(model["training_pairs"])
                or report.get("policy") != DEFAULT_POLICY
            ):
                raise EvaluatorInvalid("Candidate has not passed the release gate")
            if model["parent_model_id"] != registry["model_id"]:
                raise EvaluatorInvalid(
                    "Default changed since evaluation; evaluate a new candidate against it"
                )
            ids = [UUID(p["example_id"]) for p in model["training_pairs"]]
            # Lock corpus rows so withdrawal/deletion cannot race publication.
            examples = await conn.fetch(
                "SELECT id FROM rm_training_examples WHERE id = ANY($1::uuid[]) FOR SHARE", ids
            )
            if len(examples) != len(ids):
                raise EvaluatorInvalid("Candidate includes changed or revoked contributions")
        revision = registry["revision"] + 1
        await conn.execute(
            "INSERT INTO rm_evaluator_releases(reward_model_id, previous_model_id, registry_revision, reason) VALUES ($1,$2,$3,$4)",
            model_id,
            registry["model_id"],
            revision,
            reason,
        )
        await conn.execute(
            "UPDATE rm_evaluator_registry SET model_id = $1, revision = $2, updated_at = now() WHERE singleton",
            model_id,
            revision,
        )
        await conn.execute("""INSERT INTO rm_auto_scores(trace_id) SELECT id FROM rm_traces
            ON CONFLICT(trace_id) DO UPDATE SET attempts = 0, due_at = now(), error = NULL""")
    return {"model_id": model_id, "revision": revision}


async def reconcile() -> dict:
    """A durable sweep, bounded to 50 traces and 10 contributions per tick."""
    from ...tasks import reward_models as tasks

    pool = get_pool()
    # Recover interrupted workers. Job hard limit is 30 min; allow a margin before retry.
    await pool.execute("""UPDATE rm_scoring_runs SET status = 'failed', error = 'Scoring worker interrupted', finished_at = now()
        WHERE status = 'running' AND started_at < now() - interval '35 minutes'""")
    await pool.execute("""UPDATE rm_example_collection SET status = 'queued'
        WHERE status = 'running' AND started_at < now() - interval '35 minutes' AND attempts < 3""")
    await pool.execute("""UPDATE rm_example_collection SET status = 'failed', error = 'Collection worker interrupted'
        WHERE status = 'running' AND started_at < now() - interval '35 minutes' AND attempts >= 3""")
    await pool.execute("""UPDATE rm_example_collection SET status = 'queued'
        WHERE status = 'failed' AND due_at <= now() AND attempts < 3""")
    await pool.execute("""UPDATE rm_reward_models SET status = 'failed', error = 'Evaluator worker interrupted', finished_at = now()
        WHERE scope = 'shared' AND status = 'running' AND started_at < now() - interval '70 minutes'""")
    await schedule_candidate()
    default = await default_evaluator()
    queued = 0
    if default:
        await pool.execute(
            """UPDATE rm_auto_scores q SET error = r.error
            FROM rm_scoring_runs r, rm_traces t WHERE r.trace_id=q.trace_id AND t.id=q.trace_id
            AND r.reward_model_id=$1 AND r.trace_updated_at=t.updated_at AND r.status='failed'
            AND r.id=(SELECT id FROM rm_scoring_runs WHERE trace_id=q.trace_id AND reward_model_id=$1 ORDER BY created_at DESC LIMIT 1)""",
            default["id"],
        )
        rows = await pool.fetch(
            """SELECT t.* FROM rm_auto_scores q JOIN rm_traces t ON t.id = q.trace_id
            WHERE q.due_at <= now() AND q.attempts < 3
            AND EXISTS (SELECT 1 FROM rm_trace_steps s WHERE s.trace_id = t.id AND s.role = 'assistant' AND (s.tool_name IS NOT NULL OR btrim(s.content) <> ''))
            AND NOT EXISTS (SELECT 1 FROM rm_scoring_runs r WHERE r.trace_id = t.id AND r.reward_model_id = $1 AND r.status IN ('queued','running'))
            ORDER BY q.due_at LIMIT 50""",
            default["id"],
        )
        for trace in rows:
            _, created = await enqueue_score(
                trace["owner_user_id"], trace["id"], default["id"], automatic=True
            )
            if created:
                await pool.execute(
                    "UPDATE rm_auto_scores SET attempts = attempts + 1, due_at = now() + interval '1 minute' WHERE trace_id = $1",
                    trace["id"],
                )
                queued += 1
    # Broker outages leave the durable queued row for the next sweep.
    runs = await pool.fetch(
        "SELECT id FROM rm_scoring_runs WHERE status = 'queued' ORDER BY created_at LIMIT 50"
    )
    for run in runs:
        tasks.score_trace.delay(str(run["id"]))
    collections = await pool.fetch(
        "SELECT trace_id FROM rm_example_collection WHERE status = 'queued' AND attempts < 3 AND due_at <= now() ORDER BY due_at LIMIT 10"
    )
    for row in collections:
        tasks.collect_examples.delay(str(row["trace_id"]))
    candidates = await pool.fetch(
        "SELECT id FROM rm_reward_models WHERE scope = 'shared' AND status = 'queued' ORDER BY created_at LIMIT 1"
    )
    for row in candidates:
        tasks.train_evaluator.delay(str(row["id"]))
    return {"scoring_queued": queued, "collections_queued": len(collections)}
