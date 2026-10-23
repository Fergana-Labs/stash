"""Agent traces split into moments, each added with a label suggested from the user's reaction."""

import json

from backend.services.intuition import trace_examples

from .test_intuitions import _register

TRACE = "\n".join(
    json.dumps(row)
    for row in [
        {"trace": "agent trace", "agent": "Claude Code", "task": "Build the dashboard"},
        {"step": 1, "role": "user", "event": "message", "content": "Build the dashboard"},
        {
            "step": 2,
            "role": "agent",
            "event": "tool_call",
            "tool": "Write",
            "input": {"file_path": "Dash.tsx"},
        },
        {"step": 3, "role": "tool", "event": "tool_result", "content": "written"},
        {
            "step": 4,
            "role": "agent",
            "event": "message",
            "content": "Added a row of four big metric tiles.",
        },
        {
            "step": 5,
            "role": "user",
            "event": "message",
            "content": "eww, the numbers are way too big",
        },
        {"step": 6, "role": "agent", "event": "message", "content": "Shrunk them to 14px."},
        {"step": 7, "role": "user", "event": "message", "content": "great, now commit it"},
        {"step": 8, "role": "agent", "event": "message", "content": "Committed."},
    ]
)


def test_traces_split_into_moments_without_the_reaction_in_the_example():
    found = trace_examples.moments(trace_examples.parse(TRACE))
    assert [m["request"] for m in found] == [
        "Build the dashboard",
        "eww, the numbers are way too big",
    ]
    assert found[0]["output"] == "Added a row of four big metric tiles."
    assert found[0]["reaction"] == "eww, the numbers are way too big"
    assert any(step.startswith("agent Write:") for step in found[0]["trace"])
    assert trace_examples.parse("just some notes\nnot a trace") is None
    assert trace_examples.parse(json.dumps({"role": "user", "content": "one message"})) is None


async def test_trace_upload_adds_suggested_examples(client, monkeypatch):
    auth = await _register(client)
    made = await client.post(
        "/api/v1/intuitions",
        headers=auth,
        json={
            "name": "UI taste",
            "output_type": "preference",
            "description": "Does the UI match my taste?",
        },
    )
    model_id = made.json()["model"]["id"]
    seen = {}

    async def suggest(description, labels, found):
        seen["labels"] = [label["id"] for label in labels]
        seen["shown"] = found
        return [
            trace_examples.Verdict(
                index=0, relevant=True, label="bad", reason="the numbers are way too big"
            ),
            trace_examples.Verdict(index=1, relevant=False, label=None, reason="asked to commit"),
        ]

    monkeypatch.setattr(trace_examples, "suggest", suggest)
    resp = await client.post(
        f"/api/v1/intuitions/{model_id}/trace-examples",
        headers=auth,
        files={
            "file": ("agent trace 2026-07-10.jsonl", TRACE.encode(), "application/octet-stream")
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"added": 1}
    assert seen["labels"] == ["good", "bad"]

    examples = (await client.get(f"/api/v1/intuitions/{model_id}/examples", headers=auth)).json()
    assert len(examples) == 1
    example = examples[0]
    assert example["label"] == "bad" and example["needs_review"]
    assert example["note"] == "Suggested bad: the numbers are way too big"
    assert example["item"]["request"] == "Build the dashboard"
    assert "numbers are way too big" not in json.dumps(example["item"])

    not_trace = await client.post(
        f"/api/v1/intuitions/{model_id}/trace-examples",
        headers=auth,
        files={"file": ("notes.jsonl", b'{"a": 1}\n', "application/octet-stream")},
    )
    assert not_trace.status_code == 422
    assert "not an agent trace" in not_trace.text
