"""Owner-private calibration on trusted cached features of a released basis.

Only internal cloud workers insert features. Owners explicitly label their own
same-context pairs; these are customer feedback, not shared benchmark gold.
Every fit and prediction checks the checkpoint and live source revisions.
"""

import asyncio
import hashlib
import json
from uuid import UUID

from rm_worker.basis_manifest import validate_features, validate_manifest
from rm_worker.customer_head import compare_features, fit_customer_head

from ...database import get_pool


class HeadInvalid(ValueError):
    pass


class HeadMissing(LookupError):
    pass


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
        ).encode()
    ).hexdigest()


def _hash(value):
    if not isinstance(value, str) or len(value) != 64:
        raise HeadInvalid("An exact SHA256 input/feature digest is required")
    try:
        int(value, 16)
    except ValueError as exc:
        raise HeadInvalid("An exact SHA256 input/feature digest is required") from exc
    return value


async def basis(conn, model_id):
    row = await conn.fetchrow(
        """SELECT m.metrics FROM rm_reward_models m WHERE m.id=$1
        AND m.scope='shared' AND m.status='succeeded'
        AND EXISTS (SELECT 1 FROM rm_evaluator_releases r WHERE r.reward_model_id=m.id)
        FOR SHARE""",
        model_id,
    )
    if not row:
        raise HeadMissing("Released shared basis not found")
    manifest = (row["metrics"] or {}).get("basis_manifest")
    validate_manifest(manifest)
    _hash(manifest.get("feature_version"))
    return manifest


def check_pin(row, manifest):
    if (
        row["feature_version"] != manifest["feature_version"]
        or row["manifest_digest"] != manifest["manifest_digest"]
    ):
        raise HeadInvalid("Cached features/head belong to another shared basis")


async def pair(conn, owner, pair_id, manifest, *, model_id=None):
    row = await conn.fetchrow(
        "SELECT * FROM rm_customer_feature_pairs WHERE id=$1 AND owner_user_id=$2 FOR SHARE",
        pair_id,
        owner,
    )
    if not row:
        raise HeadMissing("Customer comparison not found")
    if model_id is not None and row["shared_model_id"] != model_id:
        raise HeadInvalid("Comparison uses another shared checkpoint")
    if row["revoked"]:
        raise HeadInvalid("Comparison has been revoked")
    check_pin(row, manifest)
    validate_features(row["features_a"], manifest)
    validate_features(row["features_b"], manifest)
    if row["trace_id"]:
        current = await conn.fetchrow(
            "SELECT updated_at FROM rm_traces WHERE id=$1 AND owner_user_id=$2 FOR SHARE",
            row["trace_id"],
            owner,
        )
        if not current or current["updated_at"] != row["trace_updated_at"]:
            raise HeadInvalid("Cached features refer to a changed or deleted trace")
    return dict(row)


async def cache_pair(
    conn,
    owner,
    model_id,
    *,
    feature_version,
    manifest_digest,
    context_digest,
    input_a_digest,
    input_b_digest,
    features_a,
    features_b,
    trace_id=None,
    trace_updated_at=None,
):
    """Trusted worker seam, not a route accepting caller-supplied feature vectors."""
    manifest = await basis(conn, model_id)
    check_pin({"feature_version": feature_version, "manifest_digest": manifest_digest}, manifest)
    for value in (context_digest, input_a_digest, input_b_digest):
        _hash(value)
    if input_a_digest == input_b_digest:
        raise HeadInvalid("A comparison needs two distinct inputs in the same context")
    a = validate_features(features_a, manifest)
    b = validate_features(features_b, manifest)
    if (trace_id is None) != (trace_updated_at is None):
        raise HeadInvalid("Trace-backed features require an exact trace version")
    provenance_digest = digest({"trace_id": trace_id, "trace_updated_at": trace_updated_at})
    if trace_id is not None:
        current = await conn.fetchrow(
            "SELECT updated_at FROM rm_traces WHERE id=$1 AND owner_user_id=$2 FOR SHARE",
            trace_id,
            owner,
        )
        if not current:
            raise HeadMissing("Owned trace not found")
        if current["updated_at"] != trace_updated_at:
            raise HeadInvalid("Trace changed during feature computation")
    row = await conn.fetchrow(
        """INSERT INTO rm_customer_feature_pairs
        (owner_user_id,shared_model_id,feature_version,manifest_digest,context_digest,
        input_a_digest,input_b_digest,features_a,features_b,trace_id,trace_updated_at,provenance_digest)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        ON CONFLICT(owner_user_id,shared_model_id,manifest_digest,context_digest,input_a_digest,input_b_digest,provenance_digest)
        DO NOTHING RETURNING id""",
        owner,
        model_id,
        feature_version,
        manifest_digest,
        context_digest,
        input_a_digest,
        input_b_digest,
        a,
        b,
        trace_id,
        trace_updated_at,
        provenance_digest,
    )
    if row:
        return {
            "id": row["id"],
            "feature_version": feature_version,
            "manifest_digest": manifest_digest,
        }
    existing = await conn.fetchrow(
        """SELECT * FROM rm_customer_feature_pairs WHERE owner_user_id=$1
        AND shared_model_id=$2 AND manifest_digest=$3 AND context_digest=$4
        AND input_a_digest=$5 AND input_b_digest=$6 AND provenance_digest=$7 FOR SHARE""",
        owner,
        model_id,
        manifest_digest,
        context_digest,
        input_a_digest,
        input_b_digest,
        provenance_digest,
    )
    if (
        not existing
        or existing["revoked"]
        or existing["features_a"] != a
        or existing["features_b"] != b
        or existing["trace_id"] != trace_id
        or existing["trace_updated_at"] != trace_updated_at
    ):
        raise HeadInvalid("Cached input has changed, conflicting or revoked feature provenance")
    return {
        "id": existing["id"],
        "feature_version": feature_version,
        "manifest_digest": manifest_digest,
    }


async def label_pair(owner, pair_id, winner):
    if winner not in ("a", "b"):
        raise HeadInvalid("Choose one alternative explicitly")
    async with get_pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT * FROM rm_customer_feature_pairs WHERE id=$1 AND owner_user_id=$2 FOR UPDATE",
            pair_id,
            owner,
        )
        if not row:
            raise HeadMissing("Customer comparison not found")
        manifest = await basis(conn, row["shared_model_id"])
        await pair(conn, owner, pair_id, manifest)
        label = 1 if winner == "a" else -1
        reference = f"authenticated_owner:{owner}"
        if (row["label"], row["label_source"], row["label_reference"]) != (
            label,
            "human",
            reference,
        ):
            await conn.execute(
                """UPDATE rm_customer_feature_pairs SET label=$3,label_source='human',
                label_reference=$4,revision=revision+1 WHERE id=$1 AND owner_user_id=$2""",
                pair_id,
                owner,
                label,
                reference,
            )
    return {"id": pair_id, "winner": winner, "source": "human"}


async def revoke_pair(owner, pair_id):
    row = await get_pool().fetchrow(
        """UPDATE rm_customer_feature_pairs SET revoked=true,revision=revision+1
        WHERE id=$1 AND owner_user_id=$2 RETURNING id""",
        pair_id,
        owner,
    )
    if not row:
        raise HeadMissing("Customer comparison not found")


def snapshot(row):
    return {"id": str(row["id"]), "revision": row["revision"], "digest": digest(row)}


def summary(row):
    return {
        k: row[k]
        for k in (
            "id",
            "name",
            "version",
            "shared_model_id",
            "feature_version",
            "manifest_digest",
            "created_at",
        )
    } | {"fit": row["head"]["fit"], "calibrated": False}


def worker_head(row):
    """Private payload for the worker; never returned by the public head API."""
    return {**row["head"], "head_id": str(row["id"]), "head_version": row["version"]}


def scoring_provenance(head, manifest):
    return {
        "evaluator_kind": manifest["evaluator_kind"],
        "feature_version": manifest["feature_version"],
        "manifest_digest": manifest["manifest_digest"],
        "customer_head_id": head["head_id"],
        "customer_head_version": head["head_version"],
        "head_snapshot_digest": digest(head),
        "score_scale": "global_training_reward_normalization",
    }


async def fit(owner, model_id, name, pair_ids, l2=1.0):
    if (
        not 1 <= len(name.strip()) <= 160
        or len(pair_ids) > 1000
        or len(set(pair_ids)) != len(pair_ids)
    ):
        raise HeadInvalid("Use a name and at most 1000 distinct comparisons")
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))", f"customer-head:{owner}:{model_id}:{name}"
        )
        manifest = await basis(conn, model_id)
        examples = [await pair(conn, owner, i, manifest, model_id=model_id) for i in pair_ids]
        if any(
            r["label"] is None or r["label_source"] not in ("human", "operator_verified")
            for r in examples
        ):
            raise HeadInvalid("Each comparison needs an explicit human or operator-approved label")
        rows = [
            {
                "chosen": r["features_a"] if r["label"] == 1 else r["features_b"],
                "rejected": r["features_b"] if r["label"] == 1 else r["features_a"],
                "feature_version": r["feature_version"],
                "manifest_digest": r["manifest_digest"],
            }
            for r in examples
        ]
        head = await asyncio.to_thread(
            fit_customer_head,
            rows,
            manifest["global_head"]["weights"],
            feature_version=manifest["feature_version"],
            manifest_digest=manifest["manifest_digest"],
            l2=l2,
        )
        head["shared_model_id"] = str(model_id)
        version = await conn.fetchval(
            "SELECT coalesce(max(version),0)+1 FROM rm_customer_heads WHERE owner_user_id=$1 AND shared_model_id=$2 AND name=$3",
            owner,
            model_id,
            name,
        )
        row = await conn.fetchrow(
            """INSERT INTO rm_customer_heads(owner_user_id,shared_model_id,name,version,
            feature_version,manifest_digest,head,example_snapshot) VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *""",
            owner,
            model_id,
            name,
            version,
            manifest["feature_version"],
            manifest["manifest_digest"],
            head,
            [snapshot(r) for r in examples],
        )
    return summary(row)


async def checked_head(conn, owner, head_id, manifest, model_id):
    row = await conn.fetchrow(
        "SELECT * FROM rm_customer_heads WHERE id=$1 AND owner_user_id=$2 FOR SHARE",
        head_id,
        owner,
    )
    if not row:
        raise HeadMissing("Customer head not found")
    if row["shared_model_id"] != model_id:
        raise HeadInvalid("Customer head uses another shared checkpoint")
    check_pin(row, manifest)
    if row["head"]["global_weights"] != manifest["global_head"]["weights"]:
        raise HeadInvalid("Customer head global prior has changed")
    for source in row["example_snapshot"]:
        current = await pair(conn, owner, UUID(source["id"]), manifest, model_id=model_id)
        if snapshot(current) != source:
            raise HeadInvalid(
                "Customer head includes changed or revoked feedback; fit a new version"
            )
    return row


async def compare(owner, model_id, pair_id, head_id=None):
    async with get_pool().acquire() as conn, conn.transaction():
        manifest = await basis(conn, model_id)
        target = await pair(conn, owner, pair_id, manifest, model_id=model_id)
        if head_id:
            row = await checked_head(conn, owner, head_id, manifest, model_id)
            head = row["head"]
        else:
            head = fit_customer_head(
                [],
                manifest["global_head"]["weights"],
                feature_version=manifest["feature_version"],
                manifest_digest=manifest["manifest_digest"],
            )
        scores = compare_features(
            target["features_a"],
            target["features_b"],
            head,
            feature_version=manifest["feature_version"],
            manifest_digest=manifest["manifest_digest"],
        )
    return scores | {
        "shared_model_id": model_id,
        "head_id": head_id,
        "feature_version": manifest["feature_version"],
        "manifest_digest": manifest["manifest_digest"],
        "context_digest": target["context_digest"],
        "pair_id": pair_id,
    }


async def detail(owner, head_id):
    row = await get_pool().fetchrow(
        "SELECT * FROM rm_customer_heads WHERE id=$1 AND owner_user_id=$2",
        head_id,
        owner,
    )
    if not row:
        raise HeadMissing("Customer head not found")
    return summary(row)


async def list_heads(owner):
    return [
        summary(r)
        for r in await get_pool().fetch(
            "SELECT * FROM rm_customer_heads WHERE owner_user_id=$1 ORDER BY created_at DESC LIMIT 100",
            owner,
        )
    ]


async def list_pairs(owner):
    return [
        dict(r)
        for r in await get_pool().fetch(
            """SELECT id,shared_model_id,feature_version,manifest_digest,context_digest,
        input_a_digest,input_b_digest,provenance_digest,trace_id,trace_updated_at,label,label_source,revoked,created_at
        FROM rm_customer_feature_pairs WHERE owner_user_id=$1 ORDER BY created_at DESC LIMIT 100""",
            owner,
        )
    ]


async def scoring_run(owner, run_id):
    async with get_pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT * FROM rm_scoring_runs WHERE id=$1 AND owner_user_id=$2 AND customer_head_id IS NOT NULL FOR SHARE",
            run_id,
            owner,
        )
        if not row:
            raise HeadMissing("Customer scoring run not found")
        result = {
            k: row[k]
            for k in (
                "id",
                "trace_id",
                "reward_model_id",
                "customer_head_id",
                "status",
                "error",
                "progress",
                "created_at",
                "finished_at",
            )
        }
        result["customer_scores"] = None
        if row["status"] == "succeeded":
            manifest = await basis(conn, row["reward_model_id"])
            checkpoint_finished_at = await conn.fetchval(
                "SELECT finished_at FROM rm_reward_models WHERE id=$1", row["reward_model_id"]
            )
            if checkpoint_finished_at != row["model_finished_at"]:
                raise HeadInvalid("Customer scores refer to a changed checkpoint")
            head_row = await checked_head(
                conn, owner, row["customer_head_id"], manifest, row["reward_model_id"]
            )
            trace = await conn.fetchrow(
                "SELECT updated_at FROM rm_traces WHERE id=$1 AND owner_user_id=$2 FOR SHARE",
                row["trace_id"],
                owner,
            )
            if not trace or trace["updated_at"] != row["trace_updated_at"]:
                raise HeadInvalid("Customer scores refer to a changed or deleted trace")
            expected = scoring_provenance(worker_head(head_row), manifest)
            expected["shared_model_id"] = str(row["reward_model_id"])
            if not row["customer_scores"] or row["customer_scores"].get("provenance") != expected:
                raise HeadInvalid("Customer scores have invalid checkpoint/head provenance")
            result["customer_scores"] = row["customer_scores"]
    return result
