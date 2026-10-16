"""Loopback-only live design journal. Exposes pixels and summaries, never history/keys."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def read_json(path, *, limit=2_000_000):
    try:
        if path.stat().st_size > limit:
            return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}  # A writer may be in the middle of saving the next receipt.


def read_jsonl(path):
    if not path.is_file():
        return []
    records = []
    for line in path.read_text().splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
        except ValueError:
            continue
    return records


@lru_cache(maxsize=4)
def experiment_summary(path, modified):
    # Frozen files contain private image references too. Read once and retain only
    # public experiment settings; never send the examples to the gallery client.
    data = read_json(path, limit=64_000_000)
    return {key: data.get(key) for key in ("tasks", "model", "label_policy", "system", "seed")}


def instructions_for(root, identity):
    if not re.fullmatch(r"[a-f0-9]{64}", identity):
        return None
    path = root / "trials.jsonl"
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        try:
            trial = json.loads(line)
        except ValueError:
            continue
        if trial.get("id") != identity:
            continue
        original = root / "experiment.json"
        frozen = (
            experiment_summary(original, original.stat().st_mtime_ns) if original.is_file() else {}
        )
        tasks = {t["id"]: t for t in frozen.get("tasks") or []}
        baseline = (root / "SKILL.md").read_text() if (root / "SKILL.md").is_file() else ""
        skill = trial.get("instructions", "")
        return {
            "id": identity,
            "skill": skill,
            "isBaseline": skill == baseline,
            "changes": "\n".join(
                difflib.unified_diff(
                    baseline.splitlines(),
                    skill.splitlines(),
                    fromfile="Starting skill",
                    tofile="Skill used for this result",
                    lineterm="",
                )
            ),
            "system": frozen.get("system") or "",
            "seed": trial.get("seed"),
            "brief": tasks.get(trial.get("task"), {}).get("brief", ""),
            "model": frozen.get("model"),
            "skillHash": hashlib.sha256(skill.encode()).hexdigest(),
        }
    return None


def judge_summary(root):
    report = read_json(root / "classifier-training.json")
    classifier = read_json(root / "classifier.json")
    invalidated = read_json(root / "pilot-invalidated.json")
    feedback_file = root / "human-feedback.jsonl"
    feedback = read_jsonl(feedback_file)
    examples = []
    for row in feedback:
        identity = row.get("trial_id", "")
        if not re.fullmatch(r"[a-f0-9]{64}", identity):
            continue
        receipt = read_json(root / "artifacts" / identity / "receipt.json")
        prediction = receipt.get("prediction", {})
        examples.append(
            {
                "id": identity,
                "image": f"/images/{identity}.png",
                "humanLabel": row.get("label"),
                "feedback": row.get("quote"),
                "score": receipt.get("classifier_score"),
                "rubric": prediction.get("rubric", {}),
                "contributions": prediction.get("contributions", {}),
            }
        )
    held = report.get("holdout", {})
    return {
        "target": "Finished website screenshot",
        "inputPipeline": [
            "Website screenshot",
            "Vision-generated description",
            "Rubric answers + generic verdict",
            "Calibrated logistic head",
        ],
        "traceRole": "Past traces supplied training examples and feedback. This classifier does not evaluate agent steps, corrections, or the full agent trace.",
        "invalidated": bool(invalidated),
        "stopReason": invalidated.get("reason"),
        "criteria": read_json(root / "criteria.json").get("rubric", []),
        "drivers": report.get("drivers", []),
        "trainingCount": report.get("counts", {}).get("train"),
        "development": {"n": held.get("n"), "accuracy": held.get("accuracy")},
        "automaticTest": {"n": classifier.get("test_n"), "accuracy": classifier.get("accuracy")},
        "examples": examples,
        "agentReports": [
            {
                "id": trial["id"],
                "task": trial["task"],
                "image": trial["image"],
                "verdict": found.get("verdict"),
                "status": found.get("status"),
                "model": found.get("model"),
            }
            for trial in snapshot(root)["trials"]
            if (found := agent_report(root, trial["id"]))
        ],
    }


def agent_report(root, identity):
    if not re.fullmatch(r"[a-f0-9]{64}", identity):
        return None
    file = root / "agent-judge" / identity / "latest.json"
    if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()):
        return None
    return read_json(file) or None


def worker_alive(pid):
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
        state = subprocess.check_output(["ps", "-p", str(pid), "-o", "stat="], text=True).strip()
        return bool(state) and not state.startswith("Z")
    except (OSError, subprocess.CalledProcessError):
        return False


def snapshot(root: Path, pid=None):
    file = root / "experiment.json"
    frozen = experiment_summary(file, file.stat().st_mtime_ns) if file.is_file() else {}
    tasks = {t["id"]: t for t in frozen.get("tasks") or []}
    baseline = (root / "SKILL.md").read_text() if (root / "SKILL.md").is_file() else None
    trials, revisions, seen = [], {}, set()
    ledger = root / "trials.jsonl"
    lines = ledger.read_text().splitlines() if ledger.is_file() else []
    feedback = root / "human-feedback.jsonl"
    human_labels = {r.get("trial_id"): r.get("label") for r in read_jsonl(feedback)}
    for line in lines:
        try:
            trial = json.loads(line)
        except ValueError:
            continue
        identity = trial.get("id", "")
        if not re.fullmatch(r"[a-f0-9]{64}", identity) or identity in seen:
            continue
        seen.add(identity)
        directory = root / "artifacts" / identity
        if directory.is_symlink() or not directory.resolve().is_relative_to(root):
            continue
        receipt = read_json(directory / "receipt.json")
        generation = read_json(directory / "generation.json")
        image = directory / "website.png"
        has_image = image.is_file() and not image.is_symlink()
        arm, instructions = trial.get("arm"), trial.get("instructions", "")
        if arm == "gepa-search":
            if instructions == baseline:
                method, method_label, revision = "skill", "Learned skill", 0
            else:
                key = hashlib.sha256(instructions.encode()).hexdigest()
                revision = revisions.setdefault(key, len(revisions) + 1)
                method, method_label = "gepa", f"GEPA · revision {revision}"
        else:
            method = {
                "dpo-sampling": "sampling",
                "posttrained": "posttrained",
                "base": "base",
                "skill": "skill",
                "gepa": "gepa",
            }.get(arm, "other")
            method_label = {
                "sampling": "Training sample",
                "posttrained": "Post-trained Qwen",
                "base": "Base Qwen",
                "skill": "Learned skill",
                "gepa": "GEPA result",
                "other": "Qwen design",
            }[method]
            revision = None
        status = (
            "scored"
            if receipt.get("valid")
            else "invalid"
            if receipt
            else "scoring"
            if has_image
            else "rendering"
            if generation
            else "generating"
        )
        stamp_file = (
            image if has_image else directory / "generation.json" if generation else directory
        )
        try:
            created = datetime.fromtimestamp(stamp_file.stat().st_mtime, UTC).isoformat()
        except OSError:
            created = None
        task = tasks.get(trial.get("task"), {})
        trials.append(
            {
                "id": identity,
                "number": len(trials) + 1,
                "task": trial.get("task", "design"),
                "brief": task.get("brief", receipt.get("brief", "")),
                "partition": task.get("partition"),
                "method": method,
                "methodLabel": method_label,
                "revision": revision,
                "seed": trial.get("seed"),
                "humanLabel": human_labels.get(identity),
                "agentJudgeFingerprint": (agent_report(root, identity) or {}).get("fingerprint"),
                "status": status,
                "score": receipt.get("classifier_score") if receipt.get("valid") else None,
                "image": f"/images/{identity}.png" if has_image else None,
                "createdAt": created,
                "outputTokens": generation.get("usage", {}).get("output_tokens"),
            }
        )
    classifier = read_json(root / "classifier.json")
    invalidated = read_json(root / "pilot-invalidated.json")
    labels = read_json(root / "auto-label-report.json")
    active = worker_alive(pid)
    completed = (root / "evaluation.json").is_file()
    trained = read_json(root / "posttraining.json")
    stages = [
        {"id": "taste", "label": "Learn your taste", "done": bool(classifier)},
        {"id": "skill", "label": "Build the skill", "done": baseline is not None},
        {"id": "gepa", "label": "Refine with GEPA", "done": (root / "gepa-result.json").is_file()},
        {
            "id": "weights",
            "label": "Train the weights",
            "done": bool(trained) and trained.get("steps") == trained.get("requested_steps"),
            "skipped": (root / "posttraining-skipped.json").is_file(),
        },
        {"id": "compare", "label": "Compare the results", "done": completed},
    ]
    stage = next((s["id"] for s in stages if not s["done"] and not s.get("skipped")), "complete")
    result = {
        "title": "Your website design run",
        "model": (frozen.get("model") or {}).get("id", "Qwen"),
        "trials": trials,
        "stages": stages,
        "currentStage": stage,
        "workerAlive": active,
        "complete": completed,
        "modelTrained": stages[3]["done"],
        "automaticLabels": frozen.get("label_policy") == "automatic_exploratory",
        "labelCount": sum(labels.get("counts", {}).values()),
        "abstentions": len(labels.get("excluded", [])),
        "classifierTestN": classifier.get("test_n"),
        "classifierAgreement": classifier.get("accuracy"),
        "humanValidated": classifier.get("independent_human_validation", False),
        "defaultTask": "research" if "research" in tasks else next(iter(tasks), "all"),
        "invalidated": bool(invalidated),
        "stopReason": invalidated.get("reason"),
        "branches": [
            {
                "id": "gepa",
                "label": "GEPA",
                "changes": "Skill instructions",
                "fixed": "Qwen weights",
                "done": (root / "gepa-result.json").is_file(),
            },
            {
                "id": "weights",
                "label": "Weight refinement",
                "changes": "Qwen weights",
                "fixed": "Original baseline skill",
                "done": stages[3]["done"],
            },
        ],
    }
    result["revision"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[
        :16
    ]
    return result


def handler(root: Path, pid=None):
    page = (
        Path(__file__)
        .with_name("gallery.html")
        .read_text()
        .replace("</head>", '<link rel="stylesheet" href="/inspector.css"></head>')
        .replace("</body>", '<script src="/inspector.js"></script></body>')
        .encode()
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, mime, *, cache="no-store"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ("/", "/index.html"):
                self.send(200, page, "text/html; charset=utf-8")
            elif path in ("/inspector.js", "/inspector.css"):
                asset = Path(__file__).with_name("gallery-" + path[1:])
                self.send(
                    200,
                    asset.read_bytes(),
                    "text/javascript" if path.endswith(".js") else "text/css",
                )
            elif path == "/api/run":
                self.send(200, json.dumps(snapshot(root, pid)).encode(), "application/json")
            elif path == "/api/judge":
                self.send(200, json.dumps(judge_summary(root)).encode(), "application/json")
            elif match := re.fullmatch(r"/api/design/([a-f0-9]{64})/instructions", path):
                data = instructions_for(root, match[1])
                self.send(
                    200 if data else 404,
                    json.dumps(data or {"error": "Unknown design"}).encode(),
                    "application/json",
                )
            elif match := re.fullmatch(r"/api/design/([a-f0-9]{64})/judge", path):
                data = agent_report(root, match[1])
                self.send(
                    200 if data else 404,
                    json.dumps(data or {"error": "No agent investigation recorded yet"}).encode(),
                    "application/json",
                )
            elif match := re.fullmatch(r"/images/([a-f0-9]{64})\.png", path):
                file = root / "artifacts" / match[1] / "website.png"
                if (
                    file.is_file()
                    and not file.is_symlink()
                    and not file.parent.is_symlink()
                    and file.resolve().is_relative_to(root)
                ):
                    self.send(200, file.read_bytes(), "image/png", cache="private, max-age=3600")
                else:
                    self.send(404, b"Image not ready", "text/plain")
            elif path == "/favicon.ico":
                self.send(204, b"", "image/x-icon")
            else:
                self.send(404, b"Not found", "text/plain")

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--port", type=int, default=3458)
    parser.add_argument("--worker-pid", type=int)
    args = parser.parse_args()
    root = args.output.resolve()
    if not root.is_dir():
        parser.error("The experiment output directory must exist")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(root, args.worker_pid))
    print(f"Design journal: http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
