"""The cloud agent's stream-json → contract-event mapping.

The fixture is a real recorded `claude -p … --output-format stream-json`
transcript (one turn with a Bash tool call), so these tests break if the
mapper drifts from what the CLI actually emits.
"""

from pathlib import Path

import pytest

from backend.config import settings
from backend.services import sprite_agent_service as svc

FIXTURE = Path(__file__).parent / "fixtures" / "claude_stream.jsonl"


def _map_fixture() -> tuple[list[dict], svc._TurnState]:
    state = svc._TurnState()
    events: list[dict] = []
    for line in FIXTURE.read_text().splitlines():
        events.extend(svc._map_line(line, state))
    return events, state


def test_fixture_maps_to_contract_events():
    events, state = _map_fixture()

    text = "".join(e["delta"] for e in events if e["type"] == "text")
    assert "DONE" in text

    tools = [e for e in events if e["type"] == "tool"]
    assert len(tools) == 1
    assert tools[0]["name"] == "Bash"
    assert "echo" in tools[0]["args"]["command"]

    results = [e for e in events if e["type"] == "tool_result"]
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert results[0]["id"] == tools[0]["id"]
    assert results[0]["name"] == "Bash"

    # The final answer comes from the result event, for persistence.
    assert state.result_text == "DONE"
    assert state.error is None


def test_thinking_and_system_lines_emit_nothing():
    state = svc._TurnState()
    for line in FIXTURE.read_text().splitlines():
        if '"type":"system"' in line.replace(" ", "") or '"thinking' in line:
            assert svc._map_line(line, state) == []


def test_error_result_sets_error():
    state = svc._TurnState()
    line = '{"type": "result", "subtype": "error_during_execution", "result": "boom"}'
    assert svc._map_line(line, state) == []
    assert state.error == "boom"


def test_redaction_strips_api_keys(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-api03-secret123")
    assert "secret123" not in svc._redact("leaked sk-ant-api03-secret123 in output")
    assert "sk-ant-other-key" not in svc._redact("also sk-ant-other-key here")


def test_claude_argv_first_turn_vs_resume():
    first = svc._claude_argv("hi", "u-u-i-d", resume=False, system_prompt="sys")
    assert first[:3] == ["claude", "-p", "hi"]
    assert "--session-id" in first and "--resume" not in first
    assert "--dangerously-skip-permissions" in first

    later = svc._claude_argv("hi", "u-u-i-d", resume=True, system_prompt="sys")
    assert "--resume" in later and "--session-id" not in later


def test_claude_argv_disallowed_tools():
    argv = svc._claude_argv(
        "hi", "u", resume=False, system_prompt="s", disallowed_tools=["Write", "Edit"]
    )
    assert argv[argv.index("--disallowedTools") + 1] == "Write,Edit"


def test_reseed_prompt_replays_history_capped():
    history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    ]
    prompt = svc._reseed_prompt(history, "new question")
    assert "first question" in prompt
    assert "first answer" in prompt
    assert prompt.endswith("new question")

    long_history = [{"role": "user", "content": "x" * 2000} for _ in range(100)]
    capped = svc._reseed_prompt(long_history, "q")
    assert len(capped) < svc._RESEED_MAX_CHARS + 1000


def test_turn_env_requires_anthropic_key_on_sprites(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError):
        svc._turn_env()


def test_turn_env_local_mode_uses_machine_login(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "local")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-whatever")
    assert svc._turn_env() == {}


def test_result_success_with_is_error_is_an_error():
    state = svc._TurnState()
    line = '{"type": "result", "subtype": "success", "is_error": true, "result": "Invalid API key"}'
    svc._map_line(line, state)
    assert state.result_text is None
    assert state.error == "Invalid API key"


def test_box_path_rejects_escapes(monkeypatch):
    from backend.services import sprite_service

    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    assert sprite_service._box_path("") == "/home/sprite"
    assert sprite_service._box_path("work/notes.md") == "/home/sprite/work/notes.md"
    assert sprite_service._box_path("/work") == "/home/sprite/work"
    for bad in ("../etc/passwd", "work/../../etc", "..", "a/../../.."):
        with pytest.raises(sprite_service.FsPathError):
            sprite_service._box_path(bad)


def test_resume_missing_detected_from_merged_stderr():
    # Sprites merges stderr into stdout, so the "no conversation found" signal
    # arrives as a non-JSON stdout line, not a separate stderr stream.
    state = svc._TurnState()
    svc._map_line("Error: No conversation found with session ID: abc", state)
    assert state.resume_missing is True
