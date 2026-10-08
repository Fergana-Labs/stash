"""Large recordings keep every target without unbounded provider prompts."""

from copy import deepcopy
from uuid import uuid4

from backend.config import settings
from backend.services.rm import step_context, step_labeler, step_labeling


def chunk(i, *, actor="agent", text=None):
    return {
        "chunk_id": f"{'u' if actor == 'user' else 'a'}{i}",
        "actor": actor,
        "kind": "user_message" if actor == "user" else "agent_message",
        "idx": i,
        "text": text or f"message {i}",
    }


def test_context_excerpts_all_large_message_roles_and_preserves_source():
    chunks = [
        chunk(0, actor="user", text="request " * 40_000),
        chunk(1, text="answer " * 40_000),
        {
            "chunk_id": "a2",
            "actor": "agent",
            "kind": "tool_call",
            "idx": 2,
            "tool": "exec",
            "args": "code " * 40_000,
            "result": "output " * 40_000,
        },
    ]
    original = deepcopy(chunks)
    [(targets, transcript)] = list(step_context.batches(chunks, 80, 200_000))
    assert targets == chunks and chunks == original
    assert len(transcript) <= 200_000
    for c in chunks:
        assert f"[{c['chunk_id']}]" in transcript
    assert transcript.count("content omitted") >= 3


def test_windows_keep_neighbors_recent_request_and_global_ids():
    chunks = [
        chunk(0, actor="user", text="Buy a burrito"),
        *[chunk(i) for i in range(1, 100)],
        chunk(100, actor="user", text="Build a web app"),
        *[chunk(i) for i in range(101, 200)],
    ]
    windows = list(step_context.batches(chunks, 80, 20_000))
    assert [c["chunk_id"] for targets, _ in windows for c in targets] == [
        c["chunk_id"] for c in chunks
    ]
    assert "[a199]" in windows[-1][1] and "Build a web app" in windows[-1][1]
    assert "[a63]" in windows[0][1] and "[a63]" in windows[1][1]
    assert all(len(text) <= 20_000 and "Excerpt of a longer trace" in text for _, text in windows)


def test_short_context_is_unchanged_and_quality_checks_also_have_a_budget():
    chunks = [chunk(0, actor="user"), chunk(1)]
    assert list(step_context.batches(chunks, 80, 200_000))[0][1] == step_labeler.render(chunks)
    chunks = [
        chunk(i, actor="user" if i % 20 == 0 else "agent", text="very long text " * 20_000)
        for i in range(120)
    ]
    state = step_labeling.check_state(chunks, chunks[-1], {"type": "other", "is_output": False})
    assert sum(len(value) for value in state.values()) <= step_labeling.JEV_STATE_CHARS
    assert "[a119]" in state["CONVERSATION"] and "[a119]" in state["STEP_TO_JUDGE"]
    assert "[u100]" in state["CONVERSATION"] and "omitted" in state["CONVERSATION"]


async def test_labels_every_target_across_windows_and_reuses_existing_labels(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(settings, "STEP_LABELING_MAX_CHUNKS", 80)
    monkeypatch.setattr(settings, "STEP_LABELING_MAX_CHARS", 200_000)
    chunks = [chunk(i, text=f"message {i} " * 1000) for i in range(165)]
    calls = []

    async def label(client, cache_key, transcript, target):
        calls.append((target["chunk_id"], cache_key))
        assert len(transcript) <= 200_000
        assert f"[{target['chunk_id']}]" in transcript
        return {"actor": "agent", "chunk_id": target["chunk_id"]}

    monkeypatch.setattr(step_labeler, "label_chunk", label)
    reused = {"a0": {"actor": "agent", "chunk_id": "a0"}}
    labels = await step_labeling.label_steps(uuid4(), chunks, reused)
    assert set(labels) == {c["chunk_id"] for c in chunks}
    assert len(calls) == 164 and calls[-1][0] == "a164"
    assert len({key for _, key in calls}) == 3
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    assert await step_labeling.label_steps(uuid4(), chunks, labels) == labels
    assert len(calls) == 164
