"""The cloud agent's transcript → contract-event mapping, per harness.

The Claude fixture is a real recorded `claude -p … --output-format stream-json`
transcript (one turn with a Bash tool call), so these break if the mapper
drifts from what the CLI actually emits.
"""

from pathlib import Path

import pytest

from backend.config import settings
from backend.services import harness as h
from backend.services import sprite_agent_service as svc

FIXTURE = Path(__file__).parent / "fixtures" / "claude_stream.jsonl"


def _map_claude_fixture() -> tuple[list[dict], h.TurnState]:
    state = h.TurnState()
    events: list[dict] = []
    for line in FIXTURE.read_text().splitlines():
        events.extend(h.map_line(h.CLAUDE, line, state))
    return events, state


def test_claude_fixture_maps_to_contract_events():
    events, state = _map_claude_fixture()

    text = "".join(e["delta"] for e in events if e["type"] == "text")
    assert "DONE" in text

    tools = [e for e in events if e["type"] == "tool"]
    assert len(tools) == 1 and tools[0]["name"] == "Bash"
    assert "echo" in tools[0]["args"]["command"]

    results = [e for e in events if e["type"] == "tool_result"]
    assert len(results) == 1 and results[0]["ok"] is True
    assert results[0]["id"] == tools[0]["id"] and results[0]["name"] == "Bash"

    assert state.result_text == "DONE" and state.error is None


def test_claude_error_result_and_is_error():
    state = h.TurnState()
    h.map_line(
        h.CLAUDE, '{"type":"result","subtype":"error_during_execution","result":"boom"}', state
    )
    assert state.error == "boom"

    state2 = h.TurnState()
    h.map_line(
        h.CLAUDE,
        '{"type":"result","subtype":"success","is_error":true,"result":"Invalid API key"}',
        state2,
    )
    assert state2.result_text is None and state2.error == "Invalid API key"


def test_resume_missing_detected_from_merged_stderr():
    # Sprites merges stderr into stdout, so this arrives as a non-JSON line.
    state = h.TurnState()
    h.map_line(h.CLAUDE, "Error: No conversation found with session ID: abc", state)
    assert state.resume_missing is True


def test_claude_uses_deterministic_id_for_create_and_resume():
    # Regression: turn 1 must CREATE the session under the deterministic id, so
    # turn 2's --resume finds it (else every turn silently reseeds).
    key = h.session_key(h.CLAUDE, "sess-1", None)

    first = h.build_argv(h.CLAUDE, "hi", session_key=key, resume=False, system_prompt="sys")
    assert first[:3] == ["claude", "-p", "hi"]
    assert first[first.index("--session-id") + 1] == key
    assert "--resume" not in first
    assert "--dangerously-skip-permissions" in first

    later = h.build_argv(h.CLAUDE, "hi", session_key=key, resume=True, system_prompt="sys")
    assert later[later.index("--resume") + 1] == key
    assert "--session-id" not in later


def test_claude_disallowed_tools():
    argv = h.build_argv(
        h.CLAUDE,
        "hi",
        session_key="k",
        resume=False,
        system_prompt="s",
        disallowed_tools=["Write", "Edit"],
    )
    assert argv[argv.index("--disallowedTools") + 1] == "Write,Edit"


def test_claude_session_key_deterministic():
    a = h.session_key(h.CLAUDE, "sess-1", None)
    b = h.session_key(h.CLAUDE, "sess-1", None)
    c = h.session_key(h.CLAUDE, "sess-2", None)
    assert a == b and a != c


# --- Codex ---


def test_codex_argv_and_resume():
    first = h.build_argv(h.CODEX, "do it", session_key=None, resume=False, system_prompt="sys")
    assert first[:2] == ["codex", "exec"]
    assert "--json" in first and "--skip-git-repo-check" in first
    assert "sys" in first[2] and "do it" in first[2]  # system prompt prepended
    assert "resume" not in first

    resumed = h.build_argv(
        h.CODEX, "more", session_key="thread_abc", resume=True, system_prompt="sys"
    )
    assert resumed[1:4] == ["exec", "resume", "thread_abc"]


def test_codex_captures_thread_id_and_maps():
    state = h.TurnState()
    h.map_line(h.CODEX, '{"type":"thread.started","thread_id":"th_123"}', state)
    assert state.native_id == "th_123"

    events = h.map_line(
        h.CODEX,
        '{"type":"item.completed","item":{"type":"command_execution","id":"c1","command":"ls","exit_code":0}}',
        state,
    )
    assert {"type": "tool", "id": "c1", "name": "Bash", "args": {"command": "ls"}} in events
    assert any(e["type"] == "tool_result" and e["ok"] for e in events)

    msg = h.map_line(
        h.CODEX,
        '{"type":"item.completed","item":{"type":"assistant_message","text":"done!"}}',
        state,
    )
    assert msg == [{"type": "text", "delta": "done!"}] and state.result_text == "done!"


# --- opencode (OpenRouter) ---


def test_opencode_argv_targets_openrouter_model():
    argv = h.build_argv(h.OPENCODE, "go", session_key=None, resume=False, system_prompt="sys")
    assert argv[:2] == ["opencode", "run"]
    m = argv[argv.index("-m") + 1]
    assert m == "openrouter/z-ai/glm-5.2"
    assert "--format" in argv and argv[argv.index("--format") + 1] == "json"
    assert "-s" not in argv

    resumed = h.build_argv(h.OPENCODE, "go", session_key="sess_x", resume=True, system_prompt="sys")
    assert resumed[resumed.index("-s") + 1] == "sess_x"


def test_opencode_captures_session_and_maps_text():
    state = h.TurnState()
    events = h.map_line(
        h.OPENCODE, '{"sessionID":"os_1","part":{"type":"text","text":"hi there"}}', state
    )
    assert state.native_id == "os_1"
    assert events == [{"type": "text", "delta": "hi there"}]


def test_opencode_error_uses_message_when_present():
    state = h.TurnState()
    h.map_line(h.OPENCODE, '{"part":{"type":"error","message":"insufficient credits"}}', state)
    assert state.error == "insufficient credits"


def test_opencode_error_without_message_keeps_raw_event():
    # An error part with no `message` must surface the raw event — reducing it
    # to the bare string "opencode error" leaves failures undiagnosable.
    state = h.TurnState()
    h.map_line(h.OPENCODE, '{"part":{"type":"error","name":"ProviderError","status":402}}', state)
    assert state.error.startswith("opencode error: ")
    assert "ProviderError" in state.error and "402" in state.error


def test_codex_error_without_message_keeps_raw_event():
    state = h.TurnState()
    h.map_line(h.CODEX, '{"type":"error","code":"rate_limited"}', state)
    assert state.error.startswith("codex error: ")
    assert "rate_limited" in state.error


def test_get_unknown_harness_raises():
    with pytest.raises(ValueError):
        h.get("nonesuch")


# --- exit-code diagnostics (_run_harness) ---


@pytest.mark.asyncio
async def test_nonzero_exit_surfaces_cli_output(monkeypatch):
    # A CLI that dies before emitting stream-json (missing binary, auth
    # failure) must report its actual output — a bare "exited with code 1"
    # is undebuggable. Injected secrets in that output must not leak.
    from backend.services import sprite_service

    async def fake_exec_stream(sprite, argv, *, env, cwd=None):
        yield {"stream": "stdout", "data": b"bash: opencode: command not found sk-live-secret\n"}
        yield {"exit_code": 127}

    monkeypatch.setattr(sprite_service, "exec_stream", fake_exec_stream)
    state = h.TurnState()
    events = [
        e
        async for e in svc._run_harness(
            h.OPENCODE,
            sprite_service.Sprite(name="s"),
            ["opencode", "run", "hi"],
            state,
            {"OPENROUTER_API_KEY": "sk-live-secret"},
        )
    ]
    assert events == []
    assert state.error.startswith("agent exited with code 127: ")
    assert "command not found" in state.error
    assert "sk-live-secret" not in state.error


@pytest.mark.asyncio
async def test_harness_emitted_error_is_redacted(monkeypatch):
    # Raw error events preserved by the mappers can echo request fragments —
    # the injected key must be scrubbed from state.error too.
    from backend.services import sprite_service

    async def fake_exec_stream(sprite, argv, *, env, cwd=None):
        yield {
            "stream": "stdout",
            "data": b'{"part":{"type":"error","detail":"auth sk-live-secret rejected"}}\n',
        }
        yield {"exit_code": 0}

    monkeypatch.setattr(sprite_service, "exec_stream", fake_exec_stream)
    state = h.TurnState()
    async for _ in svc._run_harness(
        h.OPENCODE,
        sprite_service.Sprite(name="s"),
        ["opencode", "run", "hi"],
        state,
        {"OPENROUTER_API_KEY": "sk-live-secret"},
    ):
        pass
    assert state.error.startswith("opencode error: ")
    assert "rejected" in state.error
    assert "sk-live-secret" not in state.error


# --- turn env + redaction (sprite_agent_service) ---


def test_redaction_strips_injected_key_and_sk_ant():
    env = {"ANTHROPIC_API_KEY": "sk-ant-api03-secret123"}
    assert "secret123" not in svc._redact("leaked sk-ant-api03-secret123 here", env)
    assert "sk-ant-other" not in svc._redact("also sk-ant-other-key", env)


def test_reseed_prompt_replays_history_capped():
    history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    ]
    prompt = svc._reseed_prompt(history, "new question")
    assert "first question" in prompt and "first answer" in prompt
    assert prompt.endswith("new question")

    long_history = [{"role": "user", "content": "x" * 2000} for _ in range(100)]
    assert len(svc._reseed_prompt(long_history, "q")) < svc._RESEED_MAX_CHARS + 1000


def test_box_path_rejects_escapes(monkeypatch):
    from backend.services import sprite_service

    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    assert sprite_service._box_path("") == "/home/sprite/work"
    assert sprite_service._box_path("notes.md") == "/home/sprite/work/notes.md"
    for bad in ("../etc/passwd", "../.ssh/id_rsa", "..", "a/../../.."):
        with pytest.raises(sprite_service.FsPathError):
            sprite_service._box_path(bad)
