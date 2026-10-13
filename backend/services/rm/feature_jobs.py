"""Durable, owner-private cloud features; callers cannot submit feature vectors."""

import hashlib
import json

from rm_worker.basis_manifest import validate_features

from ...database import get_pool
from . import customer_heads as heads
from . import datasets, feedback, jobs


def text_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def summary(row, *, include_inputs=False):
    result = {
        key: row[key]
        for key in (
            "id",
            "shared_model_id",
            "trace_id",
            "status",
            "attempts",
            "error",
            "pair_id",
            "feature_version",
            "manifest_digest",
            "created_at",
            "finished_at",
        )
    }
    if include_inputs:
        result["inputs"] = row["inputs"]
    return result


async def create(owner, model_id, context, task_context, a, b, trace_id=None):
    if not all(isinstance(item, dict) for item in [*context, a, b]):
        raise ValueError("Comparison requires recorded task context and two alternatives")
    if not all(feedback.is_assistant_action(item) for item in (a, b)):
        raise ValueError("Both alternatives must be assistant responses or tool calls")
    rendered = [datasets.render_action_context([*context, item], task_context) for item in (a, b)]
    if rendered[0] == rendered[1] or sum(map(len, rendered)) > 500_000:
        raise ValueError("Use distinct, bounded alternatives in the same context")
    payload = {"context": context, "task_context": task_context, "a": a, "b": b, "texts": rendered}
    async with get_pool().acquire() as conn, conn.transaction():
        manifest = await heads.basis(conn, model_id)
        updated = None
        if trace_id:
            updated = await conn.fetchval(
                "SELECT updated_at FROM rm_traces WHERE id=$1 AND owner_user_id=$2 FOR SHARE",
                trace_id,
                owner,
            )
            if updated is None:
                raise heads.HeadMissing("Owned trace not found")
        request_hash = heads.digest(
            {
                "payload": payload,
                "manifest": manifest["manifest_digest"],
                "trace_id": trace_id,
                "trace_updated_at": updated,
            }
        )
        row = await conn.fetchrow(
            """INSERT INTO rm_customer_feature_jobs
            (owner_user_id,shared_model_id,trace_id,trace_updated_at,request_hash,feature_version,manifest_digest,inputs)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(owner_user_id,shared_model_id,request_hash)
            DO UPDATE SET request_hash=EXCLUDED.request_hash RETURNING *""",
            owner,
            model_id,
            trace_id,
            updated,
            request_hash,
            manifest["feature_version"],
            manifest["manifest_digest"],
            payload,
        )
    return summary(row)


async def detail(owner, job_id):
    row = await get_pool().fetchrow(
        "SELECT * FROM rm_customer_feature_jobs WHERE id=$1 AND owner_user_id=$2", job_id, owner
    )
    if not row:
        raise heads.HeadMissing("Feature job not found")
    return summary(row, include_inputs=True)


async def retry(owner, job_id):
    """Explicitly retry a failed computation without changing its immutable inputs."""
    async with get_pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT * FROM rm_customer_feature_jobs WHERE id=$1 AND owner_user_id=$2 FOR UPDATE",
            job_id,
            owner,
        )
        if not row:
            raise heads.HeadMissing("Feature job not found")
        if row["status"] != "failed" or row["attempts"] >= 3:
            raise heads.HeadInvalid(
                "Only failed feature jobs with fewer than three attempts may retry"
            )
        manifest = await heads.basis(conn, row["shared_model_id"])
        heads.check_pin(row, manifest)
        if row["trace_id"]:
            updated = await conn.fetchval(
                "SELECT updated_at FROM rm_traces WHERE id=$1 AND owner_user_id=$2 FOR SHARE",
                row["trace_id"],
                owner,
            )
            if updated is None or updated != row["trace_updated_at"]:
                raise heads.HeadInvalid("Trace changed; create a new comparison")
        row = await conn.fetchrow(
            """UPDATE rm_customer_feature_jobs SET status='queued',error=NULL,started_at=NULL,
            finished_at=NULL,dispatched_at=NULL WHERE id=$1 RETURNING *""",
            job_id,
        )
    return summary(row)


async def run(job_id):
    pool = get_pool()
    row = await pool.fetchrow(
        """UPDATE rm_customer_feature_jobs SET status='running',started_at=now(),attempts=attempts+1,error=NULL
        WHERE id=$1 AND status='queued' RETURNING *""",
        job_id,
    )
    if not row:
        return
    try:
        async with pool.acquire() as conn, conn.transaction():
            manifest = await heads.basis(conn, row["shared_model_id"])
            heads.check_pin(row, manifest)
            key = await conn.fetchval(
                "SELECT artifact_key FROM rm_reward_models WHERE id=$1", row["shared_model_id"]
            )
        directory = jobs.job_dir(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "job.json").write_text(
            json.dumps(
                {
                    "kind": "basis_features",
                    "reward_model_key": key,
                    "feature_version": row["feature_version"],
                    "manifest_digest": row["manifest_digest"],
                }
            )
        )
        texts = row["inputs"]["texts"]
        jobs._write_jsonl(
            directory / "feature_items.jsonl",
            [{"id": side, "text": text} for side, text in zip(("a", "b"), texts, strict=True)],
        )
        await jobs.run_worker("rm_worker.modal_runner", directory)
        results = jobs._read_jsonl(directory / "features.jsonl")
        if len(results) != 2 or {item["id"] for item in results} != {"a", "b"}:
            raise ValueError("Worker returned unexpected feature inputs")
        result = {item["id"]: item for item in results}
        for side, text in zip(("a", "b"), texts, strict=True):
            item = result[side]
            heads.check_pin(item, manifest)
            validate_features(item["features"], manifest)
            if item["input_digest"] != text_digest(text):
                raise ValueError("Worker features belong to another input")
        async with pool.acquire() as conn, conn.transaction():
            # A reclaimed/cancelled job cannot publish over another worker generation.
            current = await conn.fetchrow(
                "SELECT * FROM rm_customer_feature_jobs WHERE id=$1 FOR UPDATE", job_id
            )
            if current["status"] != "running" or current["started_at"] != row["started_at"]:
                return
            cached = await heads.cache_pair(
                conn,
                row["owner_user_id"],
                row["shared_model_id"],
                feature_version=row["feature_version"],
                manifest_digest=row["manifest_digest"],
                context_digest=heads.digest(
                    {
                        "context": row["inputs"]["context"],
                        "task_context": row["inputs"]["task_context"],
                    }
                ),
                input_a_digest=result["a"]["input_digest"],
                input_b_digest=result["b"]["input_digest"],
                features_a=result["a"]["features"],
                features_b=result["b"]["features"],
                trace_id=row["trace_id"],
                trace_updated_at=row["trace_updated_at"],
            )
            await conn.execute(
                "UPDATE rm_customer_feature_jobs SET status='succeeded',pair_id=$2,finished_at=now() WHERE id=$1",
                job_id,
                cached["id"],
            )
    except Exception as exc:
        await pool.execute(
            """UPDATE rm_customer_feature_jobs SET status='failed',error=$2,finished_at=now()
            WHERE id=$1 AND status='running' AND started_at=$3""",
            job_id,
            str(exc)[-1000:],
            row["started_at"],
        )
        raise


async def reconcile():
    from ...tasks.reward_models import compute_customer_features

    pool = get_pool()
    await pool.execute("""UPDATE rm_customer_feature_jobs SET status='failed',error='Feature worker interrupted',finished_at=now()
        WHERE status='running' AND started_at<now()-interval '35 minutes'""")
    rows = await pool.fetch("""UPDATE rm_customer_feature_jobs SET dispatched_at=now()
        WHERE id IN (SELECT id FROM rm_customer_feature_jobs WHERE status='queued'
          AND (dispatched_at IS NULL OR dispatched_at<now()-interval '1 minute') ORDER BY created_at LIMIT 20)
        RETURNING id""")
    for row in rows:
        try:
            compute_customer_features.delay(str(row["id"]))
        except Exception:
            await pool.execute(
                "UPDATE rm_customer_feature_jobs SET dispatched_at=NULL WHERE id=$1 AND status='queued'",
                row["id"],
            )
    return len(rows)
