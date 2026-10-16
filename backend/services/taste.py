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
from uuid import UUID, uuid4

from scripts.website_taste.preferences import source_label, usable_label

from ..database import get_pool
from . import taste_demo
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


def cloud_enabled():
    # Demo mode only calls Claude; it never launches Modal work.
    return os.environ.get("TASTE_CLOUD_ENABLED") == "1" or taste_demo.enabled()


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
    if row["config"].get("run_id"):
        root = root / "runs" / str(UUID(row["config"]["run_id"]))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def extraction_cache(row):
    # Shared across demo resets: entries are keyed by the full extraction request
    # (prompt, model, pixels), so re-reading the same sessions reuses the answers.
    root = Path(os.environ.get("TASTE_WORKSPACE_ROOT", "/tmp/stash-taste-workspaces"))
    return root / str(row["id"]) / "extraction-cache"


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
            ["I need a few more clear examples of your feedback."]
            if sum(counts["train"].values()) < 4
            else []
        )
        + (["I need an example you clearly liked."] if not counts["train"]["liked"] else [])
        + (
            ["I need an example you clearly wanted changed."]
            if not counts["train"]["disliked"]
            else []
        ),
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
        "SELECT id,operation,status,progress,result,created_at,updated_at FROM taste_jobs WHERE workspace_id=$1 AND ($2::text IS NULL OR created_at >= $2::text::timestamptz) ORDER BY created_at DESC LIMIT 20",
        row["id"],
        row["config"].get("run_started_at"),
    )
    predictions = await get_pool().fetch(
        "SELECT id,version,output,feedback,created_at FROM taste_predictions WHERE workspace_id=$1 AND ($2::text IS NULL OR created_at >= $2::text::timestamptz) ORDER BY created_at DESC LIMIT 20",
        row["id"],
        row["config"].get("run_started_at"),
    )
    root = location(row, "experiment")
    skill = (root / "SKILL.md").read_text() if root and (root / "SKILL.md").is_file() else ""
    return {
        "id": row["id"],
        "model_id": row["config"].get("model_id"),
        "wizard_session_id": row["config"].get("wizard_session_id"),
        "published": row["config"].get("published", False),
        "fresh_start": row["config"].get("fresh_start", False),
        "name": row["name"],
        "endpoint": {
            "ready": bool(model) and row["revision"] == row["fitted_revision"],
            "path": f"/api/v1/intuitions/{row['config']['model_id']}/predict"
            if row["config"].get("model_id")
            else None,
            "quality_note": "Accuracy has not been independently established yet."
            if reasons
            else None,
        },
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
            "preferences": model.get("preferences", []),
            "examples": model.get("examples"),
        },
        "trials": trials(row),
        "jobs": [dict(j) for j in jobs],
        "predictions": [dict(p) for p in predictions],
        "skill": skill or model.get("skill", ""),
        "history": await history_bridge.status(owner),
        "sources": row["config"].get("sources", []),
        "search_coverage": row["config"].get("search_coverage", {}),
        "collection_progress": row["config"].get("collection_progress", {}),
        "related_eval_ids": row["config"].get("related_eval_ids", []),
        "cloud_enabled": cloud_enabled(),
        "demo": taste_demo.enabled(),
    }


async def review(owner, identity, label, note):
    row = await workspace(owner)
    if identity not in {e["id"] for e in effective_examples(row)}:
        raise NotFound("Example not found")
    if label not in ("liked", "disliked", "skip"):
        raise ValueError("Choose liked, disliked, or skip")
    # JSON key is parameterized; concurrent reviews merge instead of overwriting.
    await get_pool().execute(
        "UPDATE taste_workspaces SET reviews=reviews || $2::jsonb,revision=revision+1 WHERE id=$1 AND (config->>'run_id') IS NOT DISTINCT FROM $3::text",
        row["id"],
        {identity: {"label": label, "note": note}},
        row["config"].get("run_id"),
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
    elif kind == "check":
        path = work_root(row) / "runtime" / (identity + ".png")
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
    # Reset, binding, and new jobs share an owner lock. Reset cannot miss a
    # concurrently queued job and then have that job restore the old state.
    async with get_pool().acquire() as conn:
        key = owner.int % (2**63 - 1)
        await conn.execute("SELECT pg_advisory_lock($1)", key)
        try:
            return await _enqueue(owner, operation, payload)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", key)


async def _enqueue(owner, operation, payload):
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
            "upload_traces",
            "hillclimb",
        )
        and not cloud_enabled()
    ):
        raise Conflict(
            "Cloud execution is disabled for this deployment. Existing results remain available."
        )
    if operation == "build":
        gaps = label_summary(row)["build_gaps"]
        if gaps:
            raise Conflict(
                " ".join(gaps)
                + " Look through the supplied traces first; ask only about missing feedback."
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
        if op != "discover" and not cloud_enabled():
            raise ValueError("Cloud execution is disabled for this deployment.")
        if op in ("gepa", "weights", "evaluate") and blockers(row):
            raise ValueError(" ".join(blockers(row)))
        if op == "upload_traces":
            result = await learn_uploaded_traces(row, job["input"]["files"])
        elif op == "collect_all":
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
        elif op == "hillclimb":
            from . import taste_hillclimb

            directory = hillclimb_file(row, job_id).parent
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            model = grader(row)

            async def record(output):
                await pool.execute(
                    "INSERT INTO taste_predictions(workspace_id,version,input,output) VALUES($1,$2,$3,$4)",
                    row["id"],
                    model["version"],
                    {"brief": output["brief"], "screenshot_sha256": output["screenshot_sha256"]},
                    {**output, "version": model["version"], "optimization_ready": True},
                )

            result = await taste_hillclimb.run(
                hillclimb_file(row, job_id),
                work_root(row) / "runtime",
                job["input"]["brief"],
                model,
                judge_references(row),
                record,
            )
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
            if op == "build" and taste_demo.enabled():
                result = await demo_build(row)
            else:
                result = await asyncio.to_thread(execute, row, op)
            if op == "build":
                await pool.execute(
                    "UPDATE taste_workspaces SET config=config || $2::jsonb,fitted_revision=$3 WHERE id=$1",
                    row["id"],
                    {**result, **({"published": True} if job["input"].get("automatic") else {})},
                    row["revision"],
                )
                result = {"message": "Your eval is ready to call. Return its API endpoint."}
        await pool.execute(
            "UPDATE taste_jobs SET status='succeeded',progress='Completed',result=$2,updated_at=now() WHERE id=$1",
            job_id,
            result,
        )
        if job["input"].get("automatic") and op in (
            "upload_traces",
            "collect_all",
            "extract_labels",
        ):
            # Continue even if the browser was closed. Reset and new jobs share
            # this owner lock, so completed old work cannot start a new run.
            async with pool.acquire() as conn:
                key = row["owner_user_id"].int % (2**63 - 1)
                await conn.execute("SELECT pg_advisory_lock($1)", key)
                try:
                    fresh = await workspace(row["owner_user_id"])
                    same_run = all(
                        fresh["config"].get(k) == row["config"].get(k)
                        for k in ("model_id", "run_id")
                    )
                    if same_run and not label_summary(fresh)["build_gaps"]:
                        try:
                            await _enqueue(row["owner_user_id"], "build", {"automatic": True})
                        except Conflict:
                            pass  # A concurrent finish already queued the build.
                finally:
                    await conn.execute("SELECT pg_advisory_unlock($1)", key)
    except Exception as exc:
        # Provider exceptions may include request data. Keep the detailed exception
        # in worker logs, and return only bounded, credential-redacted diagnostics.
        from scripts.website_taste.evidence import clean

        await pool.execute(
            "UPDATE taste_jobs SET status='failed',progress=$2,updated_at=now() WHERE id=$1",
            job_id,
            clean(str(exc))[:1200],
        )


async def upload_traces(owner, session_id, files):
    from .intuition import wizard

    session = await wizard.get_session(owner, session_id)
    binding = await bind_wizard(owner, session)
    row = await workspace(owner)
    directory = work_root(row) / "uploads"
    saved = []
    for file in files:
        path = directory / (str(uuid4()) + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(file["content"])
        path.chmod(0o600)
        saved.append(str(path))
    queued = await enqueue(owner, "upload_traces", {"files": saved, "automatic": True})
    return {**binding, "job_id": str(queued["job_id"]), "files_received": len(files)}


def screenshot_url(url: str, out: Path) -> None:
    """Screenshot the first 1440x960 of a public web page. Private addresses are refused."""
    screenshot_page(out, url=url)


def saved_from(html: str) -> str | None:
    """The page's original address, from Chrome's "saved from url" comment or a <base> tag."""
    match = re.search(r"<!--\s*saved from url=\(\d+\)(\S+?)\s*-->", html, re.I) or re.search(
        r"<base\s[^>]*href=[\"']([^\"']+)", html, re.I
    )
    return match.group(1) if match and match.group(1).startswith(("http://", "https://")) else None


def screenshot_page(out: Path, *, url: str | None = None, html: str | None = None) -> None:
    """Screenshot the first 1440x960 of a public URL, or of uploaded HTML.

    Uploaded HTML runs with JavaScript off. Its stylesheets, fonts and images may load,
    resolved against the page's original address when the file records one. Every
    request, including redirects and subresources, must go to a public host.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    from playwright.sync_api import sync_playwright

    hosts: dict[str, bool] = {}

    def public_host(host: str) -> bool:
        if host not in hosts:
            try:
                infos = socket.getaddrinfo(host, None)
                hosts[host] = bool(infos) and all(
                    ipaddress.ip_address(i[4][0]).is_global for i in infos
                )
            except (socket.gaierror, ValueError):
                hosts[host] = False
        return hosts[host]

    def allowed(address: str) -> bool:
        parsed = urlparse(address)
        if parsed.scheme in ("data", "blob"):
            return True
        return parsed.scheme in ("http", "https") and public_host(parsed.hostname or "")

    if url is not None and (urlparse(url).scheme not in ("http", "https") or not allowed(url)):
        raise ValueError(f"{url} is not a public http(s) address.")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 960},
                device_scale_factor=1,
                java_script_enabled=html is None,
            )

            def guard(route):
                try:
                    if allowed(route.request.url):
                        route.continue_()
                        return
                except Exception:  # noqa: BLE001 -- anything unexpected is blocked
                    pass
                route.abort()

            page.route("**/*", guard)
            try:
                if html is not None:
                    base = saved_from(html)
                    if base and not re.search(r"<base\s", html, re.I):
                        tag = f'<base href="{base}">'
                        html = (
                            re.sub(
                                r"<head[^>]*>",
                                lambda m: m.group(0) + tag,
                                html,
                                count=1,
                                flags=re.I,
                            )
                            if re.search(r"<head[^>]*>", html, re.I)
                            else tag + html
                        )
                    page.set_content(html, wait_until="networkidle", timeout=25000)
                else:
                    page.goto(url, wait_until="networkidle", timeout=25000)
            except Exception:  # noqa: BLE001 -- busy pages never go idle; shoot what loaded
                page.wait_for_timeout(1500)
            page.screenshot(path=str(out), type="png", animations="disabled")
        finally:
            browser.close()


async def add_examples(owner, session_id, files):
    """Add example websites the user likes or wants changed, as confirmed training examples.

    Each file is a screenshot (PNG/JPEG/WebP), a self-contained HTML page (rendered
    with JavaScript and network disabled), or a public URL (screenshotted live).
    """
    from scripts.website_taste import evidence

    from .intuition import wizard

    session = await wizard.get_session(owner, session_id)
    binding = await bind_wizard(owner, session)
    row = await workspace(owner)
    directory = work_root(row) / "collected"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    dataset = copy.deepcopy(data(row))
    dataset.pop("sha256", None)
    dataset.setdefault("heldout_status", "not_yet_reserved")
    known = {e["id"] for e in dataset["examples"]}
    added = {"liked": 0, "disliked": 0}

    # Render pasted pages and uploaded HTML in parallel; each takes a few seconds to load.
    def key(f):
        is_html = f["name"].lower().endswith((".html", ".htm"))
        if not (f.get("url") or is_html):
            return None
        source = f["url"] if f.get("url") else f["content"]
        return directory / (hashlib.sha256(source.encode()).hexdigest() + ".page.png")

    shots = {i: key(f) for i, f in enumerate(files) if key(f)}
    await asyncio.gather(
        *(
            asyncio.to_thread(
                screenshot_page,
                out,
                url=files[i].get("url"),
                html=None if files[i].get("url") else files[i]["content"],
            )
            for i, out in shots.items()
        )
    )
    for i, file in enumerate(files):
        if i in shots:
            pixels = shots[i].read_bytes()
        else:
            pixels = base64.b64decode(file["content"], validate=True)
        if not pixels.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF")):
            raise ValueError(f"{file['name']} is not a PNG, JPEG, WebP or HTML file.")
        path = directory / (hashlib.sha256(pixels).hexdigest() + ".png")
        path.write_bytes(pixels)
        trace = {
            "steps": [],
            "coverage": {"complete": False, "reason": "Example uploaded directly"},
        }
        packet = evidence.packet(
            "Assess this website or product interface's visual design.", trace, path
        )
        if packet["id"] in known:
            continue
        label = file["label"]
        packet["supervision"] = {
            "label": label,
            "quote": f"Example you {'liked' if label == 'liked' else 'wanted changed'}: {file['name']}",
            "scope": "overall",
            "human_reviewed": True,
            "label_source": "human_example",
            "partition": "train",
            "group": "uploaded-example-" + packet["id"][:12],
            "provenance": {"reference_image": label == "liked", "uploaded_name": file["name"]},
        }
        dataset["examples"].append(packet)
        known.add(packet["id"])
        added[label] += 1
    job_id = None
    if sum(added.values()):
        write(directory / "evidence.json", dataset)
        await get_pool().execute(
            "UPDATE taste_workspaces SET config=config || $2::jsonb,revision=revision+1 WHERE id=$1",
            row["id"],
            {"dataset": str(directory)},
        )
        # Enough examples: build the grader now rather than waiting on the wizard agent.
        if not label_summary(await workspace(owner))["build_gaps"]:
            try:
                job_id = str((await enqueue(owner, "build", {"automatic": True}))["job_id"])
            except Conflict:
                pass  # A build is already running.
    return {**binding, "added": added, "job_id": job_id}


async def learn_uploaded_traces(row, paths):
    from scripts.website_taste import evidence
    from scripts.website_taste.corpus import public_events

    assets, count, screenshots = [], 0, 0
    for raw_path in paths:
        path = Path(raw_path).resolve()
        # Compare resolved paths: /tmp is a symlink to /private/tmp on macOS.
        if path.is_symlink() or not path.is_relative_to(work_root(row).resolve()):
            raise ValueError("Trace upload is outside this account's private storage")
        session_id = hashlib.sha256(path.read_bytes()).hexdigest()
        for event in public_events(path):
            if event.get("kind") != "message" or event.get("role") != "user":
                continue
            count += 1
            images = event.get("images", [])
            for index, url in enumerate(images):
                match = re.fullmatch(
                    r"data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)", url
                )
                if not match:
                    continue
                pixels = base64.b64decode(match[1])
                if len(pixels) > 8_000_000:
                    continue
                assets.append(
                    {
                        "id": f"{session_id}:{event['line']}:{index + 1}",
                        "session_id": session_id,
                        "line": event["line"],
                        "image_index": index + 1,
                        "image_count": len(images),
                        "sha256": hashlib.sha256(pixels).hexdigest(),
                        "image_base64": match[1],
                        "feedback": event["text"],
                        "trace": evidence.history_trace(path, event["line"]),
                    }
                )
                screenshots += 1
                if len(assets) == 12:
                    await propose_assets(
                        await workspace(row["owner_user_id"]), {"assets": assets}, None
                    )
                    assets = []
    if assets:
        await propose_assets(await workspace(row["owner_user_id"]), {"assets": assets}, None)
    return {
        "files_received": len(paths),
        "feedback_messages": count,
        "outputs_found": screenshots,
        "next": "Call finish to create the API. If no outputs were embedded, ask for the finished outputs needed to judge these traces.",
    }


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
    proposals = await extract_feedback(batch, extraction_cache(row))
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
    semaphore = asyncio.Semaphore(6)

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


def example_images(row):
    return {
        e["id"]: Path(e["image_file"])
        for e in data(row).get("examples", [])
        if e.get("image_file") and Path(e["image_file"]).is_file()
    }


def judge_references(row):
    return taste_demo.references(effective_examples(row), example_images(row))


def hillclimb_file(row, job_id):
    return work_root(row) / "hillclimb" / (str(UUID(str(job_id))) + ".json")


async def start_hillclimb(owner, brief):
    row = await workspace(owner)
    if not taste_demo.is_demo_grader(grader(row)):
        raise Conflict("Build your grader first.")
    return await enqueue(owner, "hillclimb", {"brief": brief})


async def hillclimb_state(owner, job_id):
    path = hillclimb_file(await workspace(owner), job_id)
    if not path.is_file():
        raise NotFound("Hill-climb not found")
    return read(path)


async def demo_build(row):
    if label_summary(row)["build_gaps"]:
        raise ValueError(" ".join(label_summary(row)["build_gaps"]))
    model = await taste_demo.build(row, effective_examples(row), example_images(row))
    directory = work_root(row) / ("demo-grader-" + str(row["revision"]))
    write(directory / "activation-probe.json", model)
    return {"probe": str(directory)}


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
                ],
                require_holdout=False,
            )
            training = [r for r in partitions if r["partition"] == "train"]
            labels = {r["id"]: r["supervision"]["label"] for r in rows}
            if len(training) < 4 or {labels[r["id"]] for r in training} != {"liked", "disliked"}:
                partitions = [{**r, "partition": "train"} for r in partitions]
            for value, assigned in zip(rows, partitions):
                value["supervision"].update(
                    partition=assigned["partition"], group=assigned["group"]
                )
            dataset["heldout_status"] = (
                "untouched_source_feedback_test"
                if any(r["supervision"]["partition"] == "test" for r in rows)
                else "not_available"
            )
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
            require_holdout=False,
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
    if item.get("url"):
        return await predict_live_page(row, item, directory, ref)
    if not item.get("screenshot_base64"):
        raise ValueError("Send a screenshot, or the URL of a local app page.")
    raw = base64.b64decode(item["screenshot_base64"], validate=True)
    if len(raw) > 4_000_000 or not raw.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
        raise ValueError("Provide a PNG or JPEG screenshot of at most 4 MB.")
    image = directory / (hashlib.sha256(raw).hexdigest() + ".png")
    image.write_bytes(raw)
    steps = [{**s, "text": evidence.clean(s["text"])} for s in item["trace"]]
    model = grader(row)
    if taste_demo.is_demo_grader(model):
        judged = await taste_demo.judge(
            model, {**item, "trace": steps}, image, judge_references(row)
        )
        output = {
            **judged,
            "version": model["version"],
            "ref": ref,
            "optimization_ready": True,
            "screenshot_sha256": image.stem,
            "brief": item["brief"][:500],
            "coverage": {
                "complete": bool(item.get("trace_complete")),
                "supplied_steps": len(steps),
            },
        }
        receipt = await get_pool().fetchval(
            "INSERT INTO taste_predictions(workspace_id,version,input,output) VALUES($1,$2,$3,$4) RETURNING id",
            row["id"],
            model["version"],
            {"brief": item["brief"], "trace": steps[-40:], "screenshot_sha256": image.stem},
            output,
        )
        return {**output, "prediction_id": str(receipt)}
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


async def predict_live_page(row, item, directory, ref):
    """Demo mode: the grader agent opens the page itself and inspects it."""
    from . import taste_grader_agent

    model = grader(row)
    if not taste_demo.is_demo_grader(model):
        raise Conflict("Live-page grading needs the demo grader.")
    shot = directory / (uuid4().hex + ".png")
    judged = await asyncio.to_thread(
        taste_grader_agent.grade, model, item, item["url"], shot, judge_references(row)
    )
    sha = hashlib.sha256(shot.read_bytes()).hexdigest()
    shot.replace(directory / (sha + ".png"))
    output = {
        **judged,
        "version": model["version"],
        "ref": ref,
        "optimization_ready": True,
        "screenshot_sha256": sha,
        "brief": item["brief"][:500],
        "coverage": {
            "complete": bool(item.get("trace_complete")),
            "supplied_steps": len(item["trace"]),
        },
    }
    receipt = await get_pool().fetchval(
        "INSERT INTO taste_predictions(workspace_id,version,input,output) VALUES($1,$2,$3,$4) RETURNING id",
        row["id"],
        model["version"],
        {"brief": item["brief"], "url": item["url"], "screenshot_sha256": sha},
        output,
    )
    return {**output, "prediction_id": str(receipt)}


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


async def reset_demo(owner, session_id):
    """Archive this demo run and begin an empty, unbound eval wizard.

    Original traces, immutable artifacts, previous sessions, prediction receipts,
    and the original compute ledger are retained. Only active demo state resets.
    """
    from .intuition import wizard

    async with get_pool().acquire() as conn:
        key = owner.int % (2**63 - 1)
        await conn.execute("SELECT pg_advisory_lock($1)", key)
        try:
            session = await wizard.get_session(owner, session_id)
            if session.get("reset_to"):
                return {"session_id": session["reset_to"], "archived": True}
            row = await workspace(owner)
            old_model = row["config"].get("model_id")
            # In demo mode any wizard chat can start the demo over; only the demo's own
            # chat is marked as reset, so an unrelated eval chat keeps working.
            from_demo_chat = session["model_id"] == old_model and (
                old_model or row["config"].get("fresh_start")
            )
            demo_chat = session_id if from_demo_chat else row["config"].get("wizard_session_id")
            if not from_demo_chat and not taste_demo.enabled():
                raise Conflict(
                    "This chat is not the current demo. Open the current demo to reset it."
                )
            if await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM taste_jobs WHERE workspace_id=$1 AND status IN ('queued','running'))",
                row["id"],
            ):
                raise Conflict(
                    "The demo is still working. Wait for its current operation to finish before resetting."
                )
            archive_id = uuid4()
            # Reserve a separate artifact root for every new run. Revisions may
            # start at zero without overwriting an archived dataset or model.
            archive = work_root(row) / "archives" / (str(archive_id) + ".json")
            write(archive, json.loads(json.dumps(row, default=str)))
            budget = location(row, "budget") or location(row, "probe") or work_root(row)
            related = list(
                dict.fromkeys(
                    [
                        *(row["config"].get("related_eval_ids") or []),
                        *([old_model] if old_model else []),
                    ]
                )
            )
            async with conn.transaction():
                new_session = await conn.fetchrow(
                    "INSERT INTO intuition_wizard_sessions(owner_user_id) VALUES($1) RETURNING id",
                    owner,
                )
                started = await conn.fetchval("SELECT clock_timestamp()")
                config = {
                    "fresh_start": True,
                    "run_id": str(uuid4()),
                    "run_started_at": started.isoformat(),
                    "wizard_session_id": str(new_session["id"]),
                    "budget": str(budget),
                    "related_eval_ids": related,
                    "archives": [*(row["config"].get("archives") or []), str(archive)],
                }
                await conn.execute(
                    "UPDATE taste_workspaces SET config=$2,reviews='{}'::jsonb,revision=0,fitted_revision=0,name='Website design' WHERE id=$1",
                    row["id"],
                    config,
                )
                await conn.execute(
                    "UPDATE intuition_wizard_sessions SET brief=brief || $3::jsonb WHERE owner_user_id=$1 AND (id=$2 OR model_id=$4)",
                    owner,
                    UUID(str(demo_chat)) if demo_chat else None,
                    {"demo_reset_to": str(new_session["id"])},
                    UUID(old_model) if old_model else None,
                )
            return {"session_id": str(new_session["id"]), "archived": True}
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", key)


async def _bind_wizard(owner, session=None, *, name="Website design"):
    """The website preference flow is a capability of the existing eval wizard."""
    from .intuition import service, wizard

    row = await workspace(owner, create=True)
    if session and (await wizard.get_session(owner, UUID(session["id"]))).get("reset_to"):
        raise Conflict("This demo was reset. Open the new wizard to continue.")
    model_id = row["config"].get("model_id")
    if not model_id and session and session.get("model_id"):
        model = await service._model(owner, UUID(session["model_id"]))
        if not model["active_version_id"]:
            model_id = str(model["id"])
    if not model_id and not session and not row["config"].get("fresh_start"):
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
        k: result[k] for k in ("id", "name", "endpoint", "labels", "examples", "jobs", "history")
    }

    result["jobs"] = [
        j for j in result["jobs"] if j["operation"] not in ("skill", "gepa", "weights", "evaluate")
    ]
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
