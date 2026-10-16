import json
from types import SimpleNamespace

import pytest

from scripts.website_taste.classifier import development_gate
from scripts.website_taste.trace_judge import PAGE, Inspection, load_packet, run


def fixture(root):
    identity = "a" * 64
    (root / "trials.jsonl").write_text(
        json.dumps({"id": identity, "task": "brief", "instructions": "Actual recorded skill"})
        + "\n"
    )
    (root / "experiment.json").write_text(
        json.dumps(
            {
                "tasks": [{"id": "brief", "brief": "Build an incident list"}],
                "examples": [
                    {"id": part, "partition": part, "quote": part + " ONLY", "label": "disliked"}
                    for part in ("train", "dev", "test")
                ],
            }
        )
    )
    directory = root / "artifacts" / identity
    directory.mkdir(parents=True)
    html = "<html>" + "actual assistant output " * 900 + "</html>"
    (directory / "generation.json").write_text(json.dumps({"text": html}))
    (directory / "website.html").write_text(html)
    (directory / "website.png").write_bytes(b"saved pixels")
    (directory / "receipt.json").write_text(json.dumps({"classifier_score": 0.9999}))
    (root / "human-feedback.jsonl").write_text("POSTHOC HUMAN LABEL MUST NOT LEAK")
    return identity


def verdict(**kwargs):
    return {
        "label": "disliked",
        "summary": "Sparse cards",
        "task_fulfillment": "Content exists",
        "correction_handling": "No corrections observed",
        "findings": [
            {
                "observation": "Large empty cards",
                "evidence": "final-render: empty incident panel",
                "trace_step_ids": ["step-3"],
                "preference_ids": ["train"],
            }
        ],
        "limitations": ["Static desktop render only"],
        **kwargs,
    }


def test_packet_contains_actual_full_trace_and_train_only_preferences(tmp_path):
    identity = fixture(tmp_path)
    packet, pixels = load_packet(tmp_path, identity)
    serialized = json.dumps(packet)
    assert "Actual recorded skill" in serialized and "actual assistant output" in serialized
    assert "train ONLY" in serialized
    assert all(x not in serialized for x in ("dev ONLY", "test ONLY", "POSTHOC", "0.9999"))
    assert pixels == b"saved pixels"
    assert "Single-turn" in packet["trace_kind"]
    with pytest.raises(ValueError, match="Unknown trial"):
        load_packet(tmp_path, "../auth")


def test_judge_cannot_finish_without_full_inspection_or_invent_citations(tmp_path):
    packet, pixels = load_packet(tmp_path, fixture(tmp_path))
    inspection = Inspection(packet, pixels)
    with pytest.raises(ValueError, match="Read every"):
        inspection.call("finish", verdict())
    inspection.call("inspect_render", {})
    for tool, content in inspection.text.items():
        for offset in range(0, len(content), PAGE):
            inspection.call(tool, {"offset": offset})
    wrong = verdict()
    wrong["findings"][0]["preference_ids"] = ["test"]
    with pytest.raises(ValueError, match="held-out"):
        inspection.call("finish", wrong)
    assert inspection.call("finish", verdict()) == {"accepted": True}
    assert inspection.audit[-2]["tool"] == "read_source"


def test_agent_loop_returns_observed_verdict_and_reuses_immutable_receipt(tmp_path):
    identity = fixture(tmp_path)
    packet, _ = load_packet(tmp_path, identity)
    steps = [
        (tool, {"offset": offset})
        for tool, text in Inspection(packet, b"pixels").text.items()
        for offset in range(0, len(text), PAGE)
    ]
    steps += [("inspect_render", {}), ("finish", verdict())]
    calls = []

    class Block:
        type = "tool_use"

        def __init__(self, name, arguments):
            self.name, self.input, self.id = name, arguments, str(len(calls))

        def model_dump(self, **kwargs):
            return {"type": self.type, "name": self.name, "input": self.input, "id": self.id}

    def create(**kwargs):
        name, arguments = steps[len(calls)]
        calls.append(name)
        return SimpleNamespace(
            content=[Block(name, arguments)], usage=SimpleNamespace(input_tokens=5, output_tokens=2)
        )

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    result = run(tmp_path, identity, client, "fake")
    assert result["verdict"]["label"] == "disliked" and not result["validated"]
    assert run(tmp_path, identity, client, "fake") == result
    assert len(calls) == len(steps)


def test_generic_like_prior_cannot_pass_development_gate():
    report = {
        "gate": {"passed": True},
        "holdout": {
            "n": 4,
            "accuracy": 0.75,
            "classification": {
                "per_class": {
                    "liked": {"support": 2, "recall": 1},
                    "disliked": {"support": 2, "recall": 0},
                }
            },
        },
    }
    assert not development_gate(report)
    report["holdout"]["classification"]["per_class"]["disliked"]["recall"] = 0.5
    assert development_gate(report)
