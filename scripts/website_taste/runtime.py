"""Actual Qwen -> isolated render -> pinned classifier, with immutable receipts.

No local model libraries are imported. Generation is supplied by a remote
provider; API/transport failures abort the experiment rather than becoming zero
preference labels. The classifier's held-out-test examples never enter its fit.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import subprocess
from pathlib import Path

import httpx

from .corpus import digest
from .protocol import SYSTEM

ROOT = Path(__file__).resolve().parents[2]


class Stash:
    def __init__(self, url: str, token: str):
        self.client = httpx.Client(
            base_url=url.rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=180
        )

    def call(self, method: str, path: str, **kwargs):
        response = self.client.request(method, "/api/v1" + path, **kwargs)
        response.raise_for_status()
        return response.json()

    def image(self, file: Path):
        cache = file.with_name(
            file.name + "." + digest(str(self.client.base_url))[:8] + ".item.json"
        )
        if cache.exists():
            return json.loads(cache.read_text())
        mime = (
            "image/jpeg"
            if file.suffix in (".jpeg", ".jpg")
            else "image/png"
            if file.suffix == ".png"
            else "image/webp"
        )
        item = self.call(
            "POST", "/intuitions/inputs", files={"file": (file.name, file.read_bytes(), mime)}
        )
        cache.write_text(json.dumps(item))
        return item


def html_only(text: str) -> str:
    text = re.sub(r"^```(?:html)?\s*|\s*```$", "", text.strip())
    if not re.match(r"<!doctype\s+html|<html[\s>]", text, re.I) or not re.search(
        r"</html>\s*$", text, re.I
    ):
        raise ValueError("Generator did not return a complete HTML document")
    return text


def render(html: Path, png: Path):
    subprocess.run(
        ["node", str(ROOT / "scripts/render_website_demo.cjs"), str(html), str(png)],
        check=True,
        timeout=45,
        capture_output=True,
    )


class Runner:
    def __init__(
        self, output: Path, experiment: dict, generate, score, *, render_fn=render, call_limit=72
    ):
        self.output, self.experiment, self.generate, self.score = (
            output,
            experiment,
            generate,
            score,
        )
        self.render = render_fn
        self.calls, self.limit = 0, call_limit
        self.output.mkdir(exist_ok=True, parents=True)
        identity = getattr(score, "identity", None)
        if identity:
            pin = self.output / "reward-pin.json"
            if pin.exists() and json.loads(pin.read_text()) != identity:
                raise ValueError(
                    "Reward changed; start a separate experiment instead of mixing GEPA results"
                )
            pin.write_text(json.dumps(identity, indent=2))
        self.log = self.output / "trials.jsonl"
        # Restarts cannot reset the request budget or silently regenerate receipts.
        if self.log.exists():
            self.calls = sum(1 for _ in self.log.open())

    def run(self, task: dict, instructions: str, arm: str, *, sample=0, adapter=None):
        seed = self.experiment["seed"] + sample
        request = {
            "experiment": self.experiment["sha256"],
            "task": task["id"],
            "instructions": instructions,
            "arm": arm,
            "seed": seed,
            "adapter": adapter,
            "reward": getattr(self.score, "identity", None),
        }
        key = digest(json.dumps(request, sort_keys=True))
        directory = self.output / "artifacts" / key
        result_file = directory / "receipt.json"
        if result_file.exists():
            return json.loads(result_file.read_text())
        if self.calls >= self.limit:
            raise ValueError("Generation budget exhausted")
        directory.mkdir(parents=True, exist_ok=True)
        messages = [
            {"role": "system", "content": SYSTEM + ("\n\n" + instructions if instructions else "")},
            {"role": "user", "content": task["brief"]},
        ]
        self.calls += 1
        with self.log.open("a") as log:
            log.write(json.dumps({"id": key, **request, "status": "started"}) + "\n")
        # Provider exceptions propagate. Empty/truncated output is an invalid design,
        # not an invented preference judgment; its zero utility is recorded separately.
        generation = self.generate(messages, seed=seed, adapter=adapter)
        if generation["model"] != self.experiment["model"]:
            raise ValueError("Generation model/revision differs from frozen experiment")
        (directory / "generation.json").write_text(json.dumps(generation, indent=2))
        receipt = {
            "id": key,
            **request,
            "brief": task["brief"],
            "partition": task["partition"],
            "model": generation["model"],
            "reward": getattr(self.score, "identity", None),
            "usage": generation.get("usage"),
            "valid": False,
            "score": 0.0,
            "classifier_score": None,
        }
        try:
            html = html_only(generation["text"])
        except ValueError as exc:
            receipt["error"] = str(exc)
        else:
            file, png = directory / "website.html", directory / "website.png"
            file.write_text(html)
            self.render(file, png)
            # Activation scorers inspect the recorded response and artifacts.
            # The legacy scorer still accepts the brief/render interface.
            if hasattr(self.score, "score_run"):
                prediction = self.score.score_run(task, messages, generation, file, png)
                score = prediction["score"]
            else:
                prediction = self.score(task["brief"], png)
                score = prediction["probabilities"]["liked"]
            if (
                not isinstance(score, (int, float))
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                raise ValueError("Classifier returned an invalid reward")
            receipt.update(
                valid=True,
                score=score,
                classifier_score=score,
                prediction=prediction,
                html=str(file),
                image=str(png),
                html_sha256=digest(html),
                png_sha256=digest(png.read_bytes()),
            )
        result_file.write_text(json.dumps(receipt, indent=2))
        return receipt


class FrozenScorer:
    def __init__(self, stash: Stash, model_id: str, version_id: str):
        self.stash, self.model_id, self.version_id = stash, model_id, version_id
        self.identity = {"model_id": model_id, "version_id": version_id}

    def __call__(self, brief: str, png: Path):
        item = self.stash.image(png)
        item = {"kind": "website", "brief": brief, "render": item}
        prediction = self.stash.call(
            "POST",
            f"/intuitions/{self.model_id}/predict",
            json={
                "item": item,
                "version_id": self.version_id,
                "caller": "website-taste-experiment",
            },
        )
        if prediction["version_id"] != self.version_id:
            raise ValueError("Prediction used a different classifier version")
        return prediction


def save_blind_gallery(output: Path, receipts: list[dict]):
    """PNG-only gallery; never execute generated HTML. Identities in a separate key."""
    import random
    from html import escape

    tasks = {}
    for receipt in receipts:
        if receipt["partition"] != "test":
            continue
        tasks.setdefault(receipt["task"], []).append(receipt)
    rng, key, sections = random.Random(713), {}, []
    for tid, candidates in tasks.items():
        rng.shuffle(candidates)
        cards = []
        for index, receipt in enumerate(candidates):
            letter = chr(65 + index)
            key[f"{tid}:{letter}"] = {"id": receipt["id"], "arm": receipt["arm"]}
            pixels = (
                base64.b64encode(Path(receipt["image"]).read_bytes()).decode()
                if receipt["valid"]
                else ""
            )
            preview = (
                f'<img src="data:image/png;base64,{pixels}" alt="Candidate {letter}">'
                if pixels
                else "<p>Generation did not produce a valid design.</p>"
            )
            cards.append(f"<article><h3>{letter}</h3>{preview}</article>")
        sections.append(
            f'<section><h2>{escape(tid)}</h2><p>{escape(candidates[0]["brief"])}</p><div class="grid">{"".join(cards)}</div><p>Record your preferred candidate, ties, or neither before revealing the key.</p></section>'
        )
    page = (
        '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'"><title>Website preference comparison</title><style>body{font:14px system-ui;margin:30px;background:#fafafa;color:#222}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}article{background:white;border:1px solid #ddd;padding:12px}img{width:100%}section{margin:40px 0}</style><h1>Which design would you choose?</h1>'
        + "".join(sections)
    )
    (output / "blind-gallery.html").write_text(page)
    (output / "reveal-key.json").write_text(json.dumps(key, indent=2))


def environment_stash():
    return Stash(os.environ["STASH_URL"], os.environ["STASH_API_KEY"])
