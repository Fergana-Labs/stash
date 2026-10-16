"""Product orchestration around the frozen taste probe.

Private bundle locations are registered by an operator, never accepted from HTTP.
The product, runtime oracle and experiments share the same versioned artifact.
All model loading/fitting stays on Modal. Read routes never launch work.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json
import os
import re
from pathlib import Path
from uuid import UUID

from scripts.website_taste.preferences import source_label, usable_label

from ..database import get_pool
from .intuition import history, history_bridge
from .intuition.service import Conflict, NotFound


def read(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.chmod(0o600)
    tmp.replace(path)


def location(row, key):
    value = row["config"].get(key)
    return Path(value).resolve() if value else None


async def workspace(owner, *, create=False):
    pool = get_pool()
    if create:
        await pool.execute(
            "INSERT INTO taste_workspaces(owner_user_id) VALUES($1) ON CONFLICT DO NOTHING", owner
        )
    row = await pool.fetchrow("SELECT * FROM taste_workspaces WHERE owner_user_id=$1", owner)
    if not row:
        raise NotFound("Create your taste workspace first")
    return dict(row)


def work_root(row):
    root = Path(os.environ.get("TASTE_WORKSPACE_ROOT", "/tmp/stash-taste-workspaces")) / str(
        row["id"]
    )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def data(row):
    probe = location(row, "dataset") or location(row, "probe")
    return read(probe / "evidence.json") if probe else {"examples": []}


def grader(row):
    probe = location(row, "probe")
    return read(probe / "activation-probe.json") if probe else {}


def effective_examples(row):
    result = []
    for item in data(row).get("examples", []):
        supervision = item["supervision"]
        review = row["reviews"].get(item["id"], {})
        label = review.get("label", supervision["label"])
        observed = source_label(supervision, pixel_sha=item["input"]["render"]["sha256"])
        reviewed = bool(review) or supervision.get("human_reviewed") is True
        usable = label in ("liked", "disliked") and (reviewed or observed)
        inferred = supervision.get("label_source") == "teacher_inferred"
        result.append(
            {
                "id": item["id"],
                "label": label,
                "suggested_label": supervision["label"],
                "reviewed": reviewed,
                "usable": usable,
                "label_status": "skipped"
                if label == "skip"
                else "confirmed"
                if reviewed
                else "from_feedback"
                if observed
                else "model_guess"
                if inferred
                else "uncertain",
                "needs_clarification": not usable
                and not inferred
                and label != "skip"
                and supervision.get("scope") not in ("functional", "unrelated")
                and (supervision.get("feedback_evidence") or {}).get("image_role")
                not in ("comparison", "unrelated"),
                "reason": (supervision.get("feedback_evidence") or {}).get("reason")
                or supervision.get("abstention", ""),
                "note": review.get("note", ""),
                "quote": supervision.get("quote", ""),
                "scope": supervision.get("scope", "overall"),
                "partition": supervision["partition"],
                "source": supervision.get("label_source", "history"),
                "coverage": item["input"]["trace"]["coverage"],
                "render_available": item["input"]["render"].get("available", False),
                "reference": supervision.get("provenance", {}).get("reference_image", False),
            }
        )
    return result


def label_summary(row):
    examples = effective_examples(row)
    usable = [e for e in examples if e["usable"]]
    partitions = {e["id"]: e["partition"] for e in usable}
    dataset = data(row)
    if dataset.get("heldout_status") == "not_yet_reserved" and usable:
        from scripts.website_taste.protocol import split_examples

        partitions = {
            e["id"]: e["partition"]
            for e in split_examples(
                [
                    {
                        "id": e["id"],
                        "session_id": e["supervision"]["group"],
                        "sha256": e["input"]["render"]["sha256"],
                    }
                    for e in dataset["examples"]
                    if e["id"] in partitions
                ]
            )
        }
    counts = {
        part: {
            label: sum(e["label"] == label and partitions[e["id"]] == part for e in usable)
            for label in ("liked", "disliked")
        }
        for part in ("train", "dev", "test")
    }
    return {
        "usable": len(usable),
        "from_feedback": sum(e["label_status"] == "from_feedback" for e in examples),
        "needs_clarification": sum(e["needs_clarification"] for e in examples),
        "model_guesses": sum(e["label_status"] == "model_guess" for e in examples),
        "liked": sum(e["label"] == "liked" for e in usable),
        "disliked": sum(e["label"] == "disliked" for e in usable),
        "partitions": counts,
        "build_gaps": (
            ["Need at least four clear training examples."]
            if sum(counts["train"].values()) < 4
            else []
        )
        + [
            f"Need clear {label} feedback in the separate {part} set."
            for part, labels in counts.items()
            for label, count in labels.items()
            if not count
        ],
    }


def blockers(row):
    model = grader(row)
    if not model:
        return ["Build your grader from the clear feedback in your history."]
    checks = model.get("release_gate", {}).get("checks", {})
    descriptions = {
        "human_reviewed_labels": "The current grader includes unverified interpretations or model guesses. Rebuild using source-grounded feedback; no blanket manual labeling is required.",
        "source_grounded_labels": "Find more clear feedback tied to its output; exclude uncertain interpretations and model guesses from fitting.",
        "fresh_human_holdout": "Validate on fresh, separate examples with clear human feedback; search history before asking for more.",
        "development_both_classes": "The development check needs at least two examples per label and adequate recall.",
        "development_agreement": "The grader has not passed the development agreement check.",
        "test_both_classes": "The final check needs examples of both liked and disliked designs.",
        "test_agreement": "The grader has not passed the final agreement check.",
    }
    reasons = [
        descriptions.get(k, k.replace("_", " ")) for k, passed in checks.items() if not passed
    ]
    probe = location(row, "probe")
    audit = read(probe / "probe-audit.json") if probe else {}
    if not model.get("release_gate", {}).get("passed") and not reasons:
        reasons.append("Grader has not passed validation.")
    if audit.get("human_failures", []):
        reasons.append("Grader disagrees with a confirmed human counterexample.")
    if row["revision"] != row["fitted_revision"]:
        reasons.append("Preferences changed. Rebuild the grader before using it for optimization.")
    return reasons


def experiment_roots(row):
    roots = [*(row["config"].get("past_experiments") or []), row["config"].get("experiment")]
    return list(dict.fromkeys(Path(p).resolve() for p in roots if p))


def trial_root(row, identity):
    for root in reversed(experiment_roots(row)):
        if (root / "artifacts" / identity / "request.json").is_file() or (
            root / "artifacts" / identity / "generation.json"
        ).is_file():
            return root
    # Some incomplete attempts only have the journal entry.
    from scripts.website_taste.gallery import snapshot

    for root in experiment_roots(row):
        if any(t["id"] == identity for t in snapshot(root)["trials"]):
            return root
    raise NotFound("Design not found")


def trials(row):
    from scripts.website_taste.gallery import snapshot

    rows = {}
    probe = location(row, "probe")
    for root in experiment_roots(row):
        if not root.exists():
            continue
        for trial in snapshot(root)["trials"]:
            receipt = read(probe / "probe-predictions" / (trial["id"] + ".json")) if probe else {}
            trial["score"] = receipt.get("prediction", {}).get("score")
            trial["grader_version"] = receipt.get("prediction", {}).get("reward", {}).get("version")
            trial.pop("agentJudgeFingerprint", None)
            rows[trial["id"]] = trial
    return list(rows.values())


async def detail(owner):
    row = await workspace(owner)
    model = grader(row)
    reasons = blockers(row)
    examples = effective_examples(row)
    jobs = await get_pool().fetch(
        "SELECT id,operation,status,progress,result,created_at,updated_at FROM taste_jobs WHERE workspace_id=$1 ORDER BY created_at DESC LIMIT 20",
        row["id"],
    )
    predictions = await get_pool().fetch(
        "SELECT id,version,output,feedback,created_at FROM taste_predictions WHERE workspace_id=$1 ORDER BY created_at DESC LIMIT 20",
        row["id"],
    )
    root = location(row, "experiment")
    skill = (root / "SKILL.md").read_text() if root and (root / "SKILL.md").is_file() else ""
    return {
        "id": row["id"],
        "model_id": row["config"].get("model_id"),
        "wizard_session_id": row["config"].get("wizard_session_id"),
        "published": row["config"].get("published", False),
        "name": row["name"],
        "revision": row["revision"],
        "fitted_revision": row["fitted_revision"],
        "examples": examples,
        "reviewed": sum(e["reviewed"] for e in examples),
        "labels": label_summary(row),
        "blockers": reasons,
        "grader": {
            "version": model.get("version"),
            "spec": model.get("spec"),
            "metrics": model.get("metrics"),
            "released": bool(model) and not reasons,
            "parameters": len(model.get("head", {}).get("weights", [])) + bool(model),
            "limitations": model.get("limitations", []),
        },
        "trials": trials(row),
        "jobs": [dict(j) for j in jobs],
        "predictions": [dict(p) for p in predictions],
        "skill": skill,
        "history": await history_bridge.status(owner),
        "sources": row["config"].get("sources", []),
        "search_coverage": row["config"].get("search_coverage", {}),
        "collection_progress": row["config"].get("collection_progress", {}),
        "related_eval_ids": row["config"].get("related_eval_ids", []),
        "cloud_enabled": os.environ.get("TASTE_CLOUD_ENABLED") == "1",
    }


async def review(owner, identity, label, note):
    row = await workspace(owner)
    if identity not in {e["id"] for e in effective_examples(row)}:
        raise NotFound("Example not found")
    if label not in ("liked", "disliked", "skip"):
        raise ValueError("Choose liked, disliked, or skip")
    # JSON key is parameterized; concurrent reviews merge instead of overwriting.
    await get_pool().execute(
        "UPDATE taste_workspaces SET reviews=reviews || $2::jsonb,revision=revision+1 WHERE id=$1",
        row["id"],
        {identity: {"label": label, "note": note}},
    )
    return await detail(owner)


def image_path(row, kind, identity):
    if not re.fullmatch("[a-f0-9]{64}", identity):
        raise NotFound("Image not found")
    if kind == "example":
        match = next((e for e in data(row).get("examples", []) if e["id"] == identity), None)
        if not match:
            raise NotFound("Image not found")
        path = Path(match["image_file"])
    else:
        if identity not in {t["id"] for t in trials(row)}:
            raise NotFound("Design not found")
        path = trial_root(row, identity) / "artifacts" / identity / "website.png"
    if not path.is_file() or path.is_symlink():
        raise NotFound("Image is unavailable")
    return path


async def inspect(owner, kind, identity):
    row = await workspace(owner)
    if kind == "example":
        match = next((e for e in data(row).get("examples", []) if e["id"] == identity), None)
        if not match:
            raise NotFound("Evidence not found")
        return {
            "input": match["input"],
            "supervision": effective_examples(row)[
                next(i for i, e in enumerate(data(row)["examples"]) if e["id"] == identity)
            ],
        }
    if identity not in {t["id"] for t in trials(row)}:
        raise NotFound("Design not found")
    from scripts.website_taste.gallery import agent_report, instructions_for

    root, probe = trial_root(row, identity), location(row, "probe")
    return {
        "instructions": instructions_for(root, identity),
        "grader_input": read(probe / "probe-predictions" / (identity + ".json")) if probe else {},
        "audit": agent_report(root, identity),
    }


async def enqueue(owner, operation, payload):
    import asyncpg

    row = await workspace(owner)
    if operation in ("gepa", "weights", "evaluate"):
        reasons = blockers(row)
        if reasons:
            raise Conflict(" ".join(reasons))
    if (
        operation
        in (
            "build",
            "gepa",
            "weights",
            "evaluate",
            "skill",
            "collect",
            "collect_all",
            "extract_labels",
        )
        and os.environ.get("TASTE_CLOUD_ENABLED") != "1"
    ):
        raise Conflict(
            "Cloud execution is disabled for this deployment. Existing results remain available."
        )
    if operation == "build":
        gaps = label_summary(row)["build_gaps"]
        if gaps:
            raise Conflict(
                " ".join(gaps)
                + " Search history for those gaps before asking the user; uncertain examples do not require a blanket review."
            )
    try:
        job = await get_pool().fetchrow(
            "INSERT INTO taste_jobs(workspace_id,operation,input) VALUES($1,$2,$3) RETURNING id",
            row["id"],
            operation,
            payload,
        )
    except asyncpg.UniqueViolationError as exc:
        raise Conflict("This workspace already has a queued or running operation.") from exc
    from ..tasks.taste import run

    try:
        run.delay(str(job["id"]))
    except Exception:
        await get_pool().execute(
            "UPDATE taste_jobs SET status='failed',progress='Could not reach the worker. Retry.',updated_at=now() WHERE id=$1",
            job["id"],
        )
        raise
    return {"job_id": job["id"]}


async def run_job(job_id):
    pool = get_pool()
    # Connection-scoped lock survives long provider calls and is released if a
    # worker dies. A redelivered running job can then resume cached work.
    async with pool.acquire() as conn:
        key = job_id.int % (2**63 - 1)
        if not await conn.fetchval("SELECT pg_try_advisory_lock($1)", key):
            return
        try:
            await _run_job(job_id)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", key)


async def _run_job(job_id):
    pool = get_pool()
    job = await pool.fetchrow(
        "UPDATE taste_jobs SET status='running',progress='Starting',updated_at=now() WHERE id=$1 AND status IN ('queued','running') RETURNING *",
        job_id,
    )
    if not job:
        return
    row = dict(
        await pool.fetchrow("SELECT * FROM taste_workspaces WHERE id=$1", job["workspace_id"])
    )
    try:
        op = job["operation"]
        if op != "discover" and os.environ.get("TASTE_CLOUD_ENABLED") != "1":
            raise ValueError("Cloud execution is disabled for this deployment.")
        if op in ("gepa", "weights", "evaluate") and blockers(row):
            raise ValueError(" ".join(blockers(row)))
        if op == "collect_all":
            result = {"sessions": 0, "messages": []}
            sources = row["config"].get("sources", [])[:10]
            if not sources:
                raise ValueError("Search for website sessions first.")
            for source in sources:
                await pool.execute(
                    "UPDATE taste_jobs SET progress=$2,updated_at=now() WHERE id=$1",
                    job_id,
                    f"Reading session {result['sessions'] + 1} of {len(sources)}",
                )
                fresh = await workspace(row["owner_user_id"])
                try:
                    part = await collect_history(
                        fresh,
                        {"source": source, "offset": source.get("match_offset", 0)},
                        job_id,
                        discover_only=False,
                    )
                except ValueError as exc:
                    part = {"source_id": source["id"], "skipped": str(exc)[:300]}
                result["sessions"] += 1
                result["messages"].append(part)
        elif op == "extract_labels":
            await pool.execute(
                "UPDATE taste_jobs SET progress='Reading your corrections and matching each one to its output',updated_at=now() WHERE id=$1",
                job_id,
            )
            result = await extract_existing_labels(row)
        elif op in ("discover", "collect"):
            result = await collect_history(
                row, job["input"], job_id, discover_only=op == "discover"
            )
        else:
            await pool.execute(
                "UPDATE taste_jobs SET progress=$2,updated_at=now() WHERE id=$1",
                job_id,
                {
                    "build": "Extracting frozen activations and fitting the head on Modal",
                    "skill": "Writing a skill from training preferences",
                    "gepa": "GEPA is refining instructions; Qwen weights stay fixed",
                    "weights": "Training weights with the original baseline skill",
                    "evaluate": "Generating the same briefs across available arms",
                }[op],
            )
            result = await asyncio.to_thread(execute, row, op)
            if op == "build":
                await pool.execute(
                    "UPDATE taste_workspaces SET config=config || $2::jsonb,fitted_revision=$3 WHERE id=$1",
                    row["id"],
                    result,
                    row["revision"],
                )
                result = {"message": "Grader built. Check validation before running experiments."}
        await pool.execute(
            "UPDATE taste_jobs SET status='succeeded',progress='Completed',result=$2,updated_at=now() WHERE id=$1",
            job_id,
            result,
        )
    except Exception as exc:
        # Provider exceptions may include request data. Keep the detailed exception
        # in worker logs, and return only bounded, credential-redacted diagnostics.
        from scripts.website_taste.evidence import clean

        await pool.execute(
            "UPDATE taste_jobs SET status='failed',progress=$2,updated_at=now() WHERE id=$1",
            job_id,
            clean(str(exc))[:1200],
        )


async def collect_history(row, payload, job_id, *, discover_only):
    owner = row["owner_user_id"]
    if discover_only:
        found = await history.search(
            owner,
            query=payload.get("query", "website"),
            limit=10,
            offset=payload.get("offset", 0),
            source=payload.get("history_source", "all"),
            event_offset=payload.get("event_offset", 0),
        )
        found = json.loads(json.dumps(found, default=str))
        # Replace the search page, preserving a cursor rather than claiming full scan.
        await get_pool().execute(
            "UPDATE taste_workspaces SET config=config || $2::jsonb WHERE id=$1",
            row["id"],
            {
                "sources": found.get("results", []),
                "search_coverage": {
                    **(
                        row["config"].get("search_coverage", {})
                        if payload.get("history_source", "all") != "all"
                        else {}
                    ),
                    **{k: v for k, v in found.items() if k != "results"},
                },
            },
        )
        return found
    source = payload["source"]
    page = await history.read(
        owner, kind=source["kind"], id=source["id"], offset=payload.get("offset", 0), limit=40
    )
    # Collected text stays separate from model supervision; missing render is explicit.
    directory = work_root(row)
    key = hashlib.sha256((source["kind"] + source["id"] + str(page["offset"])).encode()).hexdigest()
    write(directory / "history" / (key + ".json"), page)
    local_id = (
        source["id"] if source["kind"] == "local" else page.get("source", {}).get("session_id")
    )
    if not local_id:
        raise ValueError(
            "This recorded trace has no linked Codex session. Its missing rendered output cannot be judged as visual evidence."
        )
    assets = await history_bridge.request(
        owner,
        "assets",
        {
            "id": local_id,
            "offset": max(
                payload.get("asset_offset", 0),
                row["config"].get("collection_progress", {}).get(source["id"], 0),
            ),
            "limit": 2,
        },
    )
    if not assets.get("connected") or assets.get("unavailable"):
        raise ValueError("Connect local Codex history to collect the rendered outputs.")
    result = await propose_assets(row, assets, page)
    progress = {
        **row["config"].get("collection_progress", {}),
        source["id"]: assets.get("next_offset", 0),
    }
    await get_pool().execute(
        "UPDATE taste_workspaces SET config=config || $2::jsonb WHERE id=$1",
        row["id"],
        {"collection_progress": progress},
    )
    return result


async def propose_assets(row, assets, page):
    from scripts.website_taste import evidence

    directory = work_root(row) / "collected"
    dataset = copy.deepcopy(data(row))
    dataset.pop("sha256", None)
    dataset.setdefault("heldout_status", "not_yet_reserved")
    batch = []
    for asset in assets.get("assets", []):
        image = base64.b64decode(asset.pop("image_base64"), validate=True)
        path = directory / (asset["sha256"] + ".png")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(image)
        asset["feedback"] = evidence.clean(asset["feedback"])
        for step in asset["trace"]["steps"]:
            step["text"] = evidence.clean(step["text"])
        while sum(len(step["text"]) for step in asset["trace"]["steps"]) > evidence.MAX_TRACE_CHARS:
            asset["trace"]["steps"].pop(1)
            asset["trace"]["coverage"]["complete"] = False
        batch.append({**asset, "file": str(path)})
    if not batch:
        return {
            "message": "No embedded screenshots in this page. Try the next page.",
            "next_asset_offset": assets.get("next_offset"),
            "has_more": assets.get("has_more"),
        }
    proposals = await extract_feedback(batch, directory / "extractions")
    initial_count = len(dataset["examples"])
    for proposal in proposals:
        # Purely functional/unrelated screenshots are not a preference labeling queue.
        if proposal["scope"] in ("functional", "unrelated"):
            continue
        trace = proposal["trace"]
        packet = evidence.packet(
            "Assess the visual design of this website.", trace, Path(proposal["file"])
        )
        packet["supervision"] = {
            "label": proposal["label"],
            "quote": proposal["quote"],
            "preference": proposal.get("preference", ""),
            "scope": proposal["scope"],
            "feedback_evidence": proposal["feedback_evidence"],
            "abstention": proposal.get("abstention", ""),
            "human_reviewed": False,
            "label_source": "explicit_feedback_auto",
            "partition": "train",
            "group": proposal["session_id"],
            "provenance": {
                **proposal["provenance"],
                "reference_image": proposal["scope"] == "reference"
                or proposal.get("image_role") == "reference",
            },
        }
        if packet["id"] not in {e["id"] for e in dataset["examples"]}:
            dataset["examples"].append(packet)
    if len(dataset["examples"]) > initial_count:
        write(directory / "evidence.json", dataset)
        await get_pool().execute(
            "UPDATE taste_workspaces SET config=config || $2::jsonb,revision=revision+1 WHERE id=$1",
            row["id"],
            {"dataset": str(directory)},
        )
    return {
        "automatically_labeled": sum(not p["needs_review"] for p in proposals),
        "proposed": sum(p["label"] != "unknown" for p in proposals),
        "next_asset_offset": assets.get("next_offset"),
        "has_more": assets.get("has_more"),
    }


async def extract_feedback(batch, cache):
    # One selected output per request prevents a comparison message from being
    # expanded into contradictory labels for the same screenshot. Only API
    # requests run concurrently; no models are loaded on this machine.
    semaphore = asyncio.Semaphore(3)

    async def one(row):
        async with semaphore:
            return await _extract_one_feedback(row, cache)

    return [p for result in await asyncio.gather(*(one(row) for row in batch)) for p in result]


async def _extract_one_feedback(row, cache):
    from anthropic import AsyncAnthropic

    from scripts.website_taste.autolabel import pixels
    from scripts.website_taste.preferences import SYSTEM, VISUAL_SYSTEM, validate_proposals

    from ..config import settings

    # Short, server-mapped aliases prevent opaque transcript IDs from being
    # mistranscribed. Validate every returned alias before associating evidence.
    image = Path(row["file"]) if row.get("file") else None
    visible = bool(image and image.is_file())
    if visible and hashlib.sha256(image.read_bytes()).hexdigest() != row["sha256"]:
        raise ValueError("Screenshot changed before feedback extraction")
    row = {**row, "render_inspected": visible}
    batch = [row]
    system = (
        SYSTEM
        + VISUAL_SYSTEM
        + "\nThere is exactly ONE selected output in this request. Return exactly ONE proposal with id=e1, for its image_index ONLY. Other images in the same human message provide context; do not return labels for those images. If you cannot identify the selected image from the words alone, use unknown."
    )
    aliases = {"e1": row}
    payload = [
        {"id": alias, **{k: r[k] for k in ("image_index", "image_count", "feedback")}}
        for alias, r in aliases.items()
    ]
    content = [{"type": "text", "text": json.dumps(payload)}]
    if visible:
        content.append(pixels(image))
    messages = [{"role": "user", "content": content}]
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    for attempt in range(2):
        identity = hashlib.sha256(
            (system + settings.ANTHROPIC_MODEL + json.dumps(messages, sort_keys=True)).encode()
        ).hexdigest()
        file = cache / (identity + ".json")
        saved = read(file)
        if saved:
            text = saved["text"]
        else:
            reply = await AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY).messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=1500,
                system=system,
                messages=messages,
            )
            if reply.stop_reason != "end_turn":
                raise ValueError("Preference extraction was interrupted. Retry this page.")
            text = "".join(c.text for c in reply.content if c.type == "text")
            write(file, {"model": settings.ANTHROPIC_MODEL, "text": text, "sources": payload})
        try:
            response = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
            for proposal in response.get("proposals", []):
                if proposal.get("id") not in aliases:
                    raise ValueError("Extraction returned unknown evidence")
                proposal["id"] = aliases[proposal["id"]]["id"]
                if proposal.get("label") in ("liked", "disliked") and (
                    (row["image_count"] > 1 and proposal.get("target") == "single")
                    or not proposal.get("quote")
                    or proposal["quote"] not in row["feedback"]
                ):
                    raise ValueError(
                        "Use an exact source quote and the original message's image count for attribution"
                    )
            checked = validate_proposals(batch, response)
            for p in checked:
                p["feedback_evidence"]["extraction_model"] = settings.ANTHROPIC_MODEL
                p["feedback_evidence"]["extraction_receipt"] = str(file)
            return checked
        except (ValueError, TypeError, KeyError):
            if attempt:
                # One unreliable output must not block the rest of the clear
                # history or silently become an approved label.
                return validate_proposals(
                    batch,
                    {
                        "proposals": [
                            {
                                "id": row["id"],
                                "label": "unknown",
                                "scope": "overall",
                                "quote": "",
                                "explicit": False,
                                "target": "ambiguous",
                                "preference": "",
                                "reason": "Could not reliably associate this feedback with its output.",
                            }
                        ]
                    },
                )
            messages.extend(
                [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": "Invalid output. Return ONE e1 proposal. Quote an EXACT substring, preserving typos and punctuation. target refers to the ORIGINAL message: if image_count>1, single is INVALID; use explicit if the words and attached pixels identify this selected image, or ambiguous/unknown otherwise. Use unknown when uncertain.",
                    },
                ]
            )
    raise AssertionError("Unreachable")


async def extract_existing_labels(row):
    """Upgrade legacy extraction receipts, without changing frozen weights or spending GPU budget."""
    from scripts.website_taste.evidence import clean

    dataset = copy.deepcopy(data(row))
    batch = []
    for item in dataset["examples"]:
        s = item["supervision"]
        previous = s.get("feedback_evidence") or {}
        if s.get("label_source") != "explicit_feedback_auto" or (
            previous.get("render_inspected")
            and (
                source_label(s, pixel_sha=item["input"]["render"]["sha256"])
                or previous.get("explicit") is False
                or previous.get("image_role") in ("comparison", "unrelated")
            )
        ):
            continue
        # These are operator-registered local bundle receipts, never HTTP paths.
        receipt = read(Path(s.get("autolabel_receipt") or "/nonexistent-taste-receipt"))
        try:
            context = json.loads(receipt.get("prompt", "").rsplit("\n", 1)[-1])
        except (ValueError, TypeError):
            continue
        p = s.get("provenance", {})
        if not p.get("session_id") or not context.get("feedback"):
            continue
        batch.append(
            {
                "id": item["id"],
                "file": item.get("image_file"),
                **p,
                "sha256": item["input"]["render"]["sha256"],
                "feedback": clean(context["feedback"]),
                "image_count": context.get("image_count"),
            }
        )
    proposals = []
    for start in range(0, len(batch), 12):
        proposals.extend(
            await extract_feedback(batch[start : start + 12], work_root(row) / "label-extractions")
        )
    by_id = {p["id"]: p for p in proposals}
    for item in dataset["examples"]:
        if item["id"] not in by_id:
            continue
        p = by_id[item["id"]]
        item["supervision"].update(
            {
                k: p.get(k)
                for k in (
                    "label",
                    "scope",
                    "quote",
                    "preference",
                    "feedback_evidence",
                    "abstention",
                )
            }
        )
        item["supervision"].setdefault("provenance", {})["reference_image"] = (
            p["scope"] == "reference" or p.get("image_role") == "reference"
        )
    if proposals:
        dataset.pop("sha256", None)
        directory = work_root(row) / ("labels-" + str(row["revision"] + 1))
        write(directory / "evidence.json", dataset)
        await get_pool().execute(
            "UPDATE taste_workspaces SET config=config || $2::jsonb,revision=revision+1 WHERE id=$1",
            row["id"],
            {"dataset": str(directory)},
        )
    return {
        "labels": label_summary(await workspace(row["owner_user_id"])),
        "message": "Clear feedback is usable automatically. Uncertain cases and model guesses remain excluded. Frozen grader unchanged.",
    }


def execute(row, operation):
    from scripts.website_taste import experiment, protocol
    from scripts.website_taste.probe_pipeline import (
        ProbeScorer,
        extract_features,
        feature_path,
        fit_probe,
    )
    from scripts.website_taste.runtime import Runner

    probe, root = location(row, "probe"), location(row, "experiment")
    if operation == "build":
        gaps = label_summary(row)["build_gaps"]
        if gaps:
            raise ValueError(" ".join(gaps))
        dataset = copy.deepcopy(data(row))
        rows = []
        for value in dataset["examples"]:
            review = row["reviews"].get(value["id"])
            if review and review["label"] == "skip":
                continue
            if review:
                value["supervision"].update(
                    label=review["label"],
                    human_reviewed=True,
                    label_source="human_review",
                    review_note=review["note"],
                )
            if usable_label(value["supervision"], pixel_sha=value["input"]["render"]["sha256"]):
                rows.append(value)
        if not rows:
            raise ValueError(
                "No clear feedback tied to an output. Search history for more evidence or ask a targeted question."
            )
        if {
            r["supervision"]["label"] for r in rows if r["supervision"]["partition"] == "train"
        } != {"liked", "disliked"}:
            raise ValueError("The training set needs both liked and disliked examples.")
        directory = work_root(row) / ("version-" + str(row["revision"]))
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if dataset.get("heldout_status") == "not_yet_reserved":
            partitions = protocol.split_examples(
                [
                    {
                        "id": v["id"],
                        "session_id": v["supervision"]["group"],
                        "sha256": v["input"]["render"]["sha256"],
                    }
                    for v in rows
                ]
            )
            for value, assigned in zip(rows, partitions):
                value["supervision"].update(
                    partition=assigned["partition"], group=assigned["group"]
                )
            dataset["heldout_status"] = "untouched_source_feedback_test"
        elif row["revision"] != row["fitted_revision"] and grader(row):
            dataset["heldout_status"] = "previously_inspected_test"
        experiment_dir = directory / "generation"
        experiment_dir.mkdir(exist_ok=True)
        original = read(root / "experiment.json") if root else {}
        examples = [
            {
                "id": v["id"],
                "sha256": v["input"]["render"]["sha256"],
                "label": v["supervision"]["label"],
                "partition": v["supervision"]["partition"],
                "group": v["supervision"]["group"],
                "quote": v["supervision"].get("quote", ""),
                "preference": v["supervision"].get("preference", ""),
                "review_note": v["supervision"].get("review_note", ""),
                "human_reviewed": v["supervision"].get("human_reviewed", False),
                "label_source": v["supervision"].get("label_source", "human_review"),
                "scope": v["supervision"].get("scope"),
                "feedback_evidence": v["supervision"].get("feedback_evidence"),
                "needs_review": False,
            }
            for v in rows
        ]
        frozen = protocol.seal(
            experiment_dir,
            examples,
            original.get("tasks") or protocol.tasks(),
            original.get("model")
            or {"id": "Qwen/Qwen3-8B", "revision": "b968826d9c46dd6066d109eabc6255188de91218"},
            label_policy="source_grounded",
        )
        dataset.update(
            examples=rows, label_policy="source_grounded", source_experiment=frozen["sha256"]
        )
        dataset.pop("sha256", None)
        dataset["sha256"] = hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest()
        write(directory / "evidence.json", dataset)
        # Reuse the exact frozen representation, but share the original compute
        # ledger so new versions cannot reset the approved allowance.
        for item in rows:
            cached = feature_path(probe, item["id"]) if probe else Path("/nonexistent-taste-cache")
            if cached.is_file():
                target = feature_path(directory, item["id"])
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(cached.read_bytes())
        budget = location(row, "budget") or work_root(row)
        extract_features(directory, rows, budget_output=budget)
        fit_probe(directory, budget_output=budget)
        # Reuse frozen saved-design vectors for new head scores. This is a small
        # dot product, not local inference/training, and spends no cloud budget.
        refresh_saved_scores(row, probe, directory)
        return {
            "probe": str(directory),
            "dataset": str(directory),
            "budget": str(budget),
            "experiment": str(experiment_dir),
            "past_experiments": [str(p) for p in experiment_roots(row)],
        }
    if not root:
        raise ValueError("Build a grader and reserve experiment tasks before running experiments.")
    if operation == "skill":
        if row["revision"] != row["fitted_revision"]:
            raise ValueError("Build from source-grounded preferences before writing the skill.")
        experiment.make_skill(root, experiment.Reflector(root, "claude-sonnet-4-6"))
        return {"skill": "ready"}
    scorer = ProbeScorer(probe, budget_output=location(row, "budget"))
    frozen = protocol.load(root)
    from scripts.website_taste.probe_pipeline import dataset_at

    if dataset_at(probe)["source_experiment"] != frozen["sha256"]:
        raise ValueError("Grader and generation experiment identities differ.")
    if not (root / "SKILL.md").is_file():
        raise ValueError("Write the original skill before starting either experiment.")
    if (root / "pilot-invalidated.json").exists():
        raise ValueError("This experiment was invalidated. Build a new grader version first.")
    from scripts.website_taste.cloud import RemoteGenerator

    runner = Runner(
        root,
        frozen,
        RemoteGenerator(frozen["model"]),
        scorer,
        call_limit=frozen["max_generation_calls"],
    )
    if operation == "gepa":
        result = experiment.optimize(root, runner, experiment.Reflector(root, "claude-sonnet-4-6"))
        return {"candidates": len(result["candidates"])}
    if operation == "weights":
        import modal

        pairs = experiment.dpo_pairs(root, runner)
        config, identity = experiment.training_identity(frozen, pairs, scorer.identity)
        if (root / "posttraining.json").exists():
            raise ValueError(
                "Weight training already has a receipt; inspect it before another run."
            )
        result = modal.Function.from_name("stash-website-taste", "train").remote(
            frozen["model"], pairs, config, identity
        )
        write(root / "posttraining.json", result)
        return {"adapter": result["adapter"]}
    adapter = read(root / "posttraining.json").get("adapter")
    result = experiment.evaluate(root, runner, adapter=adapter)
    return {"arms": result["arms"]}


async def predict(owner, item, *, ref=None):
    row = await workspace(owner)
    if not grader(row):
        raise Conflict("Build the taste grader first.")
    # Exploratory calls are useful for inspection; they cannot enable optimization.
    from scripts.website_taste import evidence
    from scripts.website_taste.probe_pipeline import ProbeScorer

    directory = work_root(row) / "runtime"
    directory.mkdir(exist_ok=True, mode=0o700)
    raw = base64.b64decode(item["screenshot_base64"], validate=True)
    if len(raw) > 4_000_000 or not raw.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
        raise ValueError("Provide a PNG or JPEG screenshot of at most 4 MB.")
    image = directory / (hashlib.sha256(raw).hexdigest() + ".png")
    image.write_bytes(raw)
    steps = [{**s, "text": evidence.clean(s["text"])} for s in item["trace"]]
    total = len(steps)
    while sum(len(s["text"]) for s in steps) > evidence.MAX_TRACE_CHARS:
        steps.pop(1 if len(steps) > 2 else 0)
    trace = {
        "steps": steps,
        "coverage": {
            "complete": item.get("trace_complete", False) and len(steps) == total,
            "supplied_steps": total,
            "selected_steps": len(steps),
            "reason": "Coverage declared by calling agent",
        },
    }
    packet = evidence.packet(item["brief"], trace, image, source=item.get("html", ""))
    model = grader(row)
    require_compute_or_cache(row, packet)
    score = await asyncio.to_thread(
        ProbeScorer(
            location(row, "probe"), exploratory=True, budget_output=location(row, "budget")
        ).score_packet,
        packet,
    )
    output = {
        **score,
        "version": model["version"],
        "ref": ref,
        "optimization_ready": not blockers(row),
        "coverage": trace["coverage"],
    }
    receipt = await get_pool().fetchval(
        "INSERT INTO taste_predictions(workspace_id,version,input,output) VALUES($1,$2,$3,$4) RETURNING id",
        row["id"],
        model["version"],
        packet["input"],
        output,
    )
    return {**output, "prediction_id": str(receipt)}


async def compare(owner, a, b, winner):
    row = await workspace(owner)
    found = {t["id"]: t for t in trials(row)}
    if a == b or a not in found or b not in found or winner not in (a, b, "tie"):
        raise ValueError("Select two distinct designs and a preference.")
    if found[a]["task"] != found[b]["task"] or found[a]["brief"] != found[b]["brief"]:
        raise ValueError("Compare designs from the same website brief.")
    if not found[a]["image"] or not found[b]["image"]:
        raise ValueError("Both designs need rendered outputs.")
    key = "comparison:" + hashlib.sha256(":".join(sorted([a, b])).encode()).hexdigest()
    await get_pool().execute(
        "UPDATE taste_workspaces SET reviews=reviews || $2::jsonb WHERE id=$1",
        row["id"],
        {
            key: {
                "a": a,
                "b": b,
                "winner": winner,
                "source": "human",
                "grader_version": grader(row).get("version"),
            }
        },
    )
    return {"saved": True, "claim": "Human preference, stored separately from classifier rewards."}


async def check_design(owner, identity):
    """Score known saved evidence through the same oracle, reusing frozen activations."""
    row = await workspace(owner)
    if identity not in {t["id"] for t in trials(row)}:
        raise NotFound("Design not found")
    from scripts.website_taste import evidence
    from scripts.website_taste.probe_pipeline import ProbeScorer

    packet = evidence.from_trial(trial_root(row, identity), identity)
    require_compute_or_cache(row, packet)
    scorer = ProbeScorer(
        location(row, "probe"), exploratory=True, budget_output=location(row, "budget")
    )
    output = await asyncio.to_thread(scorer.score_packet, packet)
    output.update(
        version=scorer.probe["version"],
        optimization_ready=not blockers(row),
        coverage=packet["input"]["trace"]["coverage"],
        ref="saved-design:" + identity,
    )
    saved = await get_pool().fetchval(
        "INSERT INTO taste_predictions(workspace_id,version,input,output) VALUES($1,$2,$3,$4) RETURNING id",
        row["id"],
        output["version"],
        packet["input"],
        output,
    )
    return {**output, "prediction_id": str(saved)}


async def checkpoint(owner, identity):
    row = await workspace(owner)
    found = await get_pool().fetchrow(
        "SELECT id,version,input,output,feedback,created_at FROM taste_predictions WHERE workspace_id=$1 AND id=$2",
        row["id"],
        identity,
    )
    if not found:
        raise NotFound("Checkpoint not found")
    return dict(found)


def require_compute_or_cache(row, packet):
    from scripts.website_taste.probe_pipeline import feature_path

    if (
        os.environ.get("TASTE_CLOUD_ENABLED") != "1"
        and not feature_path(location(row, "probe"), packet["id"]).is_file()
    ):
        raise Conflict("Cloud execution is disabled. Existing cached checkpoints remain available.")


def refresh_saved_scores(row, old, new):
    if not old:
        return
    from scripts.website_taste import activation_head
    from scripts.website_taste.gallery import read_jsonl
    from scripts.website_taste.probe_pipeline import REPRESENTATION, SPEC, feature_path, load_probe

    model = load_probe(new)
    truths = {}
    for root in experiment_roots(row):
        for item in read_jsonl(root / "human-feedback.jsonl"):
            if item.get("label") in ("liked", "disliked"):
                truths[item.get("trial_id")] = item["label"]
    unresolved = []
    previous = read(old / "probe-audit.json")
    for identity in previous.get("human_failures", []):
        unresolved.append(identity)
    for path in (old / "probe-predictions").glob("*.json"):
        receipt = read(path)
        prediction = receipt.get("prediction", {})
        input_id = prediction.get("input_id", "")
        if not re.fullmatch("[a-f0-9]{64}", input_id):
            continue
        cached = read(feature_path(old, input_id))
        if (
            cached.get("spec") != SPEC
            or cached.get("id") != input_id
            or cached.get("pixel_sha256")
            != receipt.get("inputs", {}).get("render", {}).get("sha256")
        ):
            continue
        output = activation_head.predict(model["head"], cached["activation"])
        output.update(
            input_id=input_id,
            generated_tokens=0,
            reward={
                "kind": model["kind"],
                "version": model["version"],
                "dataset": model["dataset"],
                "representation": REPRESENTATION,
            },
        )
        receipt["prediction"] = output
        write(new / "probe-predictions" / path.name, receipt)
        target = feature_path(new, input_id)
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(feature_path(old, input_id).read_bytes())
        identity = receipt.get("trial_id")
        if identity in unresolved and truths.get(identity) == output["label"]:
            unresolved.remove(identity)
    write(
        new / "probe-audit.json",
        {
            "version": model["version"],
            "human_failures": unresolved,
            "policy": "Only agreement with an explicitly recorded human label resolves a known counterexample; agent verdicts do not.",
        },
    )


async def bind_wizard(owner, session=None, *, name="Website design"):
    async with get_pool().acquire() as conn:
        key = owner.int % (2**63 - 1)
        await conn.execute("SELECT pg_advisory_lock($1)", key)
        try:
            return await _bind_wizard(owner, session, name=name)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", key)


async def _bind_wizard(owner, session=None, *, name="Website design"):
    """The website preference flow is a capability of the existing eval wizard."""
    from .intuition import service, wizard

    row = await workspace(owner, create=True)
    model_id = row["config"].get("model_id")
    if not model_id and session and session.get("model_id"):
        model = await service._model(owner, UUID(session["model_id"]))
        if not model["active_version_id"]:
            model_id = str(model["id"])
    if not model_id and not session:
        existing = await get_pool().fetchrow(
            "SELECT s.id,s.model_id FROM intuition_wizard_sessions s JOIN intuition_models m ON m.id=s.model_id WHERE s.owner_user_id=$1 AND lower(m.name)='website design' AND m.active_version_id IS NULL ORDER BY s.updated_at DESC LIMIT 1",
            owner,
        )
        if existing:
            model_id = str(existing["model_id"])
            session = await wizard.get_session(owner, existing["id"])
    if not model_id:
        model = await service.create_model(
            owner,
            name=name,
            output_type="choice",
            description="Does the agent’s website match my visual preferences, based on its trace and rendered output?",
            labels=[
                {"id": "liked", "description": "I would keep this design"},
                {"id": "disliked", "description": "I would request visual changes"},
            ],
            rubric=[],
        )
        model_id = str(model["model"]["id"])
    if not session:
        saved = row["config"].get("wizard_session_id")
        if saved:
            try:
                session = await wizard.get_session(owner, UUID(saved))
            except NotFound:
                pass
        if not session:
            session = await wizard.create_session(owner, UUID(model_id))
    session["model_id"] = model_id
    model = await service._model(owner, UUID(model_id))
    session["title"] = model["name"]
    await wizard._save(session)
    await get_pool().execute(
        "UPDATE taste_workspaces SET name=$2,config=config || $3::jsonb WHERE id=$1",
        row["id"],
        model["name"],
        {"model_id": model_id, "wizard_session_id": session["id"]},
    )
    return {"session_id": session["id"], "model_id": model_id}


async def wizard_state(owner, model_id):
    try:
        row = await workspace(owner)
    except NotFound:
        return None
    if row["config"].get("model_id") != str(model_id):
        return None
    result = await detail(owner)
    result = {
        k: result[k]
        for k in (
            "id",
            "name",
            "grader",
            "reviewed",
            "labels",
            "blockers",
            "examples",
            "jobs",
            "history",
            "skill",
            "trials",
        )
    }
    # The agent must not mistake a discarded extraction guess for an accepted
    # human label. The product API retains the original guess for inspection.
    result["examples"] = [
        e if e["usable"] else {**e, "label": "unknown", "suggested_label": "unknown"}
        for e in result["examples"]
    ]
    return result


async def mapped_model(owner, model_id):
    row = await get_pool().fetchrow(
        "SELECT * FROM taste_workspaces WHERE owner_user_id=$1 AND config->>'model_id'=$2",
        owner,
        str(model_id),
    )
    return dict(row) if row else None
