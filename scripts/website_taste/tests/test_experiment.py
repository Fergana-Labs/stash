import json

import pytest

from scripts.website_taste import corpus, protocol
from scripts.website_taste.cloud_worker import require_cloud
from scripts.website_taste.preferences import validate_proposals
from scripts.website_taste.runtime import FrozenScorer, Runner, html_only, save_blind_gallery


def test_only_public_human_and_assistant_messages_are_exposed(tmp_path):
    path = tmp_path / "trace.jsonl"
    entries = [
        {
            "type": "response_item",
            "payload": {"type": "message", "role": role, "content": [{"text": value}]},
        }
        for role, value in [
            ("system", "secret"),
            ("developer", "secret"),
            ("user", "# AGENTS.md instructions"),
            ("user", "Make this website denser"),
            ("assistant", "Done"),
        ]
    ]
    entries.append(
        {"type": "response_item", "payload": {"type": "reasoning", "summary": "private"}}
    )
    path.write_text("\n".join(json.dumps(x) for x in entries))
    assert [e["text"] for e in corpus.public_events(path)] == ["Make this website denser", "Done"]


def test_recovery_requires_complete_literal_source_and_never_executes_code():
    html = "<!doctype html><html><body>Hello</body></html>"
    patch = "*** Begin Patch\n*** Add File: index.html\n+" + html + "\n*** End Patch"
    assert corpus.complete_writes({"name": "apply_patch", "arguments": patch}) == [
        ("index.html", html + "\n")
    ]
    wrapped = "text(await tools.apply_patch(" + json.dumps(patch) + "));"
    assert corpus.complete_writes({"name": "exec", "arguments": wrapped}) == [
        ("index.html", html + "\n")
    ]
    assert corpus.complete_writes({"name": "exec", "arguments": wrapped + "evil();"}) == []
    assert corpus.patch_additions("*** Update File: index.html\n@@\n-Old\n+New") == []
    assert (
        corpus.complete_writes(
            {"name": "exec_command", "arguments": {"cmd": "python -c 'execute_historical_code()'"}}
        )
        == []
    )


def test_invalid_quote_abstains_and_cross_source_evidence_is_rejected():
    source = {
        "id": "one",
        "feedback": "Make the rows thinner",
        "session_id": "s",
        "line": 2,
        "image_index": 1,
        "sha256": "p",
    }
    result = validate_proposals(
        [source],
        {"proposals": [{"id": "one", "label": "liked", "scope": "overall", "quote": "I love it"}]},
    )
    assert result[0]["label"] == "unknown" and result[0]["needs_review"]
    with pytest.raises(ValueError, match="unknown or duplicate"):
        validate_proposals([source], {"proposals": [{"id": "other"}]})


def test_duplicate_pixels_and_stash_worktrees_cannot_cross_splits():
    rows = [
        {"id": str(i), "session_id": str(i), "sha256": str(i), "project": p}
        for i, p in enumerate(
            [
                "/Users/h/projects/stash",
                "/Users/h/projects/stash-worktrees/demo",
                "/projects/b",
                "/projects/c",
                "/projects/d",
            ]
        )
    ]
    rows[3]["sha256"] = rows[2]["sha256"]
    split = protocol.split_examples(rows)
    assert split[0]["group"] == split[1]["group"]
    assert split[2]["group"] == split[3]["group"]
    assert len({r["partition"] for r in split}) == 3


def test_freeze_blocks_unreviewed_or_one_sided_data(tmp_path):
    rows = []
    for group, partition in enumerate(("train", "dev", "test")):
        for label in ("liked", "disliked"):
            rows.append(
                {
                    "id": f"{group}:{label}",
                    "label": label,
                    "needs_review": False,
                    "group": str(group),
                    "partition": partition,
                    "sha256": f"{group}:{label}",
                }
            )
    model = {"id": "Qwen/Qwen3-8B", "revision": "pinned"}
    frozen = protocol.seal(tmp_path, rows, protocol.tasks(), model)
    assert protocol.load(tmp_path)["sha256"] == frozen["sha256"]
    with pytest.raises(ValueError, match="Review"):
        protocol.validate_dataset([{**r, "needs_review": True} for r in rows], protocol.tasks())
    with pytest.raises(ValueError, match="both preference"):
        protocol.validate_dataset([r for r in rows if r["label"] == "liked"], protocol.tasks())
    file = tmp_path / "experiment.json"
    changed = json.loads(file.read_text())
    changed["seed"] += 1
    file.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="modified"):
        protocol.load(tmp_path)


def test_real_runner_keeps_receipts_and_does_not_grade_instructions(tmp_path):
    calls, scores = [], []
    spec = {"id": "Qwen/Qwen3-8B", "revision": "pinned"}

    def generate(messages, **kwargs):
        calls.append(messages)
        return {"text": "<html><body>Result</body></html>", "model": spec}

    def render(html, png):
        png.write_bytes(b"pixels")

    def score(brief, png):
        scores.append((brief, png))
        return {"probabilities": {"liked": 0.7}}

    runner = Runner(
        tmp_path, {"seed": 1, "sha256": "frozen", "model": spec}, generate, score, render_fn=render
    )
    task = {"id": "t", "brief": "A new website", "partition": "test"}
    result = runner.run(task, "Private skill instructions", "skill")
    assert result["score"] == 0.7 and scores[0][0] == task["brief"]
    assert "Private skill instructions" not in str(scores)
    assert runner.run(task, "Private skill instructions", "skill") == result
    assert len(calls) == 1
    save_blind_gallery(tmp_path, [result])
    gallery = (tmp_path / "blind-gallery.html").read_text()
    assert "Private skill" not in gallery and "<body>Result" not in gallery


def test_transport_failure_is_not_a_bad_preference_label(tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("Provider disconnected")

    runner = Runner(tmp_path, {"seed": 1, "sha256": "frozen"}, fail, fail)
    with pytest.raises(RuntimeError, match="Provider disconnected"):
        runner.run({"id": "t", "brief": "Task", "partition": "train"}, "", "base")
    assert not list(tmp_path.rglob("receipt.json"))


def test_generation_context_and_cloud_guard():
    assert html_only("```html\n<html>Hello</html>\n```") == "<html>Hello</html>"
    with pytest.raises(ValueError):
        html_only("Here is a partial document <html>")
    with pytest.raises(RuntimeError, match="never be loaded"):
        require_cloud()


def test_gpu_payload_excludes_private_history_and_test_evidence():
    config = {
        "sha256": "frozen",
        "seed": 1,
        "dpo_steps": 40,
        "dpo_beta": 0.1,
        "examples": [{"feedback": "private history", "data_url": "private pixels"}],
        "tasks": [{"partition": "test", "brief": "held out"}],
    }
    remote = protocol.cloud_training_config(config)
    assert "private" not in json.dumps(remote) and "held out" not in json.dumps(remote)
    assert remote["sha256"] == "frozen" and remote["dpo_steps"] == 40


def test_pinned_scorer_passes_version_and_checks_receipt(tmp_path):
    class Fake:
        def image(self, file):
            return {"kind": "image", "content": "Pixels"}

        def call(self, method, path, **kwargs):
            assert kwargs["json"]["version_id"] == "frozen"
            assert "instructions" not in kwargs["json"]["item"]
            return {"version_id": "wrong"}

    with pytest.raises(ValueError, match="different classifier"):
        FrozenScorer(Fake(), "model", "frozen")("New brief", tmp_path / "png")


def test_actual_gepa_library_optimizes_instructions_on_dev_not_test(tmp_path):
    pytest.importorskip("gepa")
    from scripts.website_taste.experiment import optimize

    examples = [
        {
            "id": f"{partition}:{label}",
            "label": label,
            "needs_review": False,
            "group": partition,
            "partition": partition,
            "sha256": f"{partition}:{label}",
        }
        for partition in ("train", "dev", "test")
        for label in ("liked", "disliked")
    ]
    spec = {"id": "test-only-fake", "revision": "test"}
    frozen = protocol.seal(tmp_path, examples, protocol.tasks(), spec)
    (tmp_path / "SKILL.md").write_text("Use spacious rows")
    seen = []

    def generate(messages, **kwargs):
        seen.append(messages[-1]["content"])
        result = "compact" if "compact" in messages[0]["content"] else "spacious"
        return {"text": f"<html><body>{result}</body></html>", "model": spec}

    def render(html, png):
        png.write_text(html.read_text())

    def score(brief, png):
        return {"probabilities": {"liked": 0.8 if "compact" in png.read_text() else 0.2}}

    runner = Runner(tmp_path, frozen, generate, score, render_fn=render)
    result = optimize(tmp_path, runner, lambda prompt: "```\nUse compact rows\n```")
    assert len(result["candidates"]) >= 2
    assert result["candidates"][result["best_index"]]["dev_reward"] == pytest.approx(0.8)
    assert not set(seen) & {t["brief"] for t in protocol.tasks() if t["partition"] == "test"}


def test_weight_evaluation_does_not_require_or_consume_gepa(tmp_path, monkeypatch):
    from scripts.website_taste import experiment

    monkeypatch.setattr(
        experiment,
        "load",
        lambda output: {"sha256": "frozen", "tasks": [{"id": "test", "partition": "test"}]},
    )
    monkeypatch.setattr(experiment, "save_blind_gallery", lambda *args: None)
    (tmp_path / "SKILL.md").write_text("Original baseline")
    seen = []

    class Fake:
        def run(self, task, instruction, arm, **kwargs):
            seen.append((instruction, arm, kwargs["adapter"]))
            return {"id": arm}

    report = experiment.evaluate(tmp_path, Fake(), adapter="weights-only")
    assert report["arms"] == ["base", "skill", "posttrained"]
    assert seen[-1] == ("Original baseline", "posttrained", "weights-only")
    (tmp_path / "GEPA-SKILL.md").write_text("Optimized instructions")
    report = experiment.evaluate(tmp_path, Fake(), adapter="weights-only")
    assert "gepa" in report["arms"]
    assert seen[-1] == ("Original baseline", "posttrained", "weights-only")


def test_automatic_labels_require_explicit_exploratory_policy(tmp_path):
    rows = [
        {
            "id": f"{part}:{label}",
            "group": part,
            "partition": part,
            "sha256": f"{part}:{label}",
            "label": label,
            "needs_review": True,
            "human_reviewed": False,
            "accepted_for_exploration": True,
            "label_source": "teacher_inferred",
            "autolabel_receipt": "receipt.json",
        }
        for part in ("train", "dev", "test")
        for label in ("liked", "disliked")
    ]
    with pytest.raises(ValueError, match="Review preference"):
        protocol.seal(tmp_path, rows, protocol.tasks(), {})
    with pytest.raises(ValueError, match="Review preference"):
        protocol.validate_dataset([{**r, "needs_review": False} for r in rows], protocol.tasks())
    frozen = protocol.seal(
        tmp_path, rows, protocol.tasks(), {}, label_policy="automatic_exploratory"
    )
    assert protocol.load(tmp_path)["label_policy"] == "automatic_exploratory"
    assert all(e["needs_review"] and not e["human_reviewed"] for e in frozen["examples"])
    rows[0].pop("autolabel_receipt")
    with pytest.raises(ValueError, match="Review preference"):
        protocol.validate_dataset(rows, protocol.tasks(), label_policy="automatic_exploratory")


def test_automatic_history_labels_cannot_invent_quotes_or_label_functionality():
    from scripts.website_taste.autolabel import validate

    row = {"session_id": "s", "feedback": "Copy this table layout please"}
    result = {"label": "liked", "scope": "reference", "quote": row["feedback"], "confidence": 0.95}
    assert validate(row, result)["label"] == "liked"
    assert validate(row, {**result, "quote": "Human approved every detail"})["label"] == "unknown"
    assert validate(row, {**result, "scope": "functional"})["label"] == "unknown"


def test_auto_label_profile_excludes_holdout_and_preserves_manual_queue(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import anthropic

    from scripts.website_taste import autolabel

    source, output = tmp_path / "manual", tmp_path / "auto"
    source.mkdir()
    image = source / "pixels.png"
    image.write_bytes(b"pixels")
    rows = [
        {
            "id": f"{part}:{label}",
            "partition": part,
            "split": "train" if part == "train" else "eval",
            "session_id": "s" if part == "train" else None,
            "feedback": "Training " + label,
            "file": str(image),
            "native_id": "original-" + part + label,
            "item": {"brief": f"fresh {part} {label}"},
            "generation_prompt": "NEVER_REVEAL_STYLE_PROMPT",
        }
        for part in ("train", "dev", "test")
        for label in ("liked", "disliked")
    ]
    original = json.dumps({"examples": rows})
    (source / "calibration.json").write_text(original)
    calls = []

    def create(**kwargs):
        prompt = kwargs["messages"][0]["content"][0]["text"]
        assert "NEVER_REVEAL_STYLE_PROMPT" not in prompt
        calls.append(prompt)
        if prompt.startswith("Infer only"):
            assert "fresh dev" not in prompt and "fresh test" not in prompt
            result = {"preferences": [{"rule": "Clear rows", "source_ids": ["train:liked"]}]}
        else:
            context = json.loads(prompt.rsplit("\n", 1)[-1])
            text = context.get("feedback") or context["brief"]
            result = {
                "label": text.split()[-1],
                "scope": "reference",
                "confidence": 0.95,
                "quote": context.get("feedback", ""),
                "preference": "Clear rows",
                "reason": "Evidence",
            }
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(result))],
            usage=SimpleNamespace(model_dump=lambda: {}),
        )

    monkeypatch.setattr(
        anthropic, "Anthropic", lambda: SimpleNamespace(messages=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(autolabel, "pixels", lambda _: {"type": "image"})

    class Native:
        requests = []

        def call(self, method, path, **kwargs):
            assert method == "POST"  # Never edits the original native examples.
            self.requests.append((path, kwargs))
            identity = "new-" + str(len(self.requests))
            if path == "/intuitions":
                return {"model": {"id": identity}}
            if path == "/model-wizard/sessions":
                return {"id": identity}
            return [{"id": identity}]

    result = autolabel.prepare(source, output, Native(), model="fake")
    assert result["examples"] == 6 and len(calls) == 7
    assert (source / "calibration.json").read_text() == original
    accepted = [json.loads(s) for s in (output / "reviewed.jsonl").read_text().splitlines()]
    assert all(not r["human_reviewed"] and r["needs_review"] for r in accepted)
