"""Loopback-only live design journal. Exposes pixels and summaries, never history/keys."""

from __future__ import annotations

import argparse
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


@lru_cache(maxsize=4)
def experiment_summary(path, modified):
    # Frozen files contain private image references too. Read once and retain only
    # public experiment settings; never send the examples to the gallery client.
    data = read_json(path, limit=64_000_000)
    return {key: data.get(key) for key in ("tasks", "model", "label_policy")}


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
                "status": status,
                "score": receipt.get("classifier_score") if receipt.get("valid") else None,
                "image": f"/images/{identity}.png" if has_image else None,
                "createdAt": created,
                "outputTokens": generation.get("usage", {}).get("output_tokens"),
            }
        )
    classifier = read_json(root / "classifier.json")
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
    }
    result["revision"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[
        :16
    ]
    return result


def handler(root: Path, pid=None):
    page = Path(__file__).with_name("gallery.html").read_bytes()

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
                "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
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
            elif path == "/api/run":
                self.send(200, json.dumps(snapshot(root, pid)).encode(), "application/json")
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
