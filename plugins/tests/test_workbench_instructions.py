"""Native hooks emit released context, never infer a load from disk or fetch."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

import pytest

from stashai.plugin.event import HookEvent
from stashai.plugin.workbench import instruction_context, released_instruction_context


def delivery(text="Check recorded test results before claiming success."):
    return {
        "id": str(uuid4()),
        "change_id": str(uuid4()),
        "content": text,
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "status": "offered",
    }


class DeliveryClient:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error
        self.calls = []

    def workbench_instruction_delivery(self, *args):
        self.calls.append(args)
        if self.error:
            raise self.error
        return {"deliveries": self.items}


def test_exact_released_content_and_identifiers_enter_context():
    item = delivery("Check zero.\nKeep this whitespace.\n")
    client = DeliveryClient([item])
    event = HookEvent(kind="session_start", session_id="run1", cwd="/repo")
    context = released_instruction_context(client, {"client": "codex_cli"}, event)
    assert context == instruction_context(item)
    assert "\n" + item["content"] + "\n</stash-workbench-instruction>" in context
    assert item["id"] in context and item["change_id"] in context
    assert client.calls == [("run1", "codex", "/repo")]
    # Fetching/printing is only an offer, not proof the model received context.
    assert item["status"] == "offered"


@pytest.mark.parametrize("corruption", ["text", "hash", "id"])
def test_corrupt_delivery_is_not_injected(corruption):
    item = delivery()
    if corruption == "text":
        item["content"] += " changed after hashing"
    elif corruption == "hash":
        item["content_sha256"] = "bad"
    else:
        item["id"] = "not-a-uuid"
    context = released_instruction_context(
        DeliveryClient([item]),
        {"client": "codex_cli"},
        HookEvent(kind="session_start", session_id="run1", cwd="/repo"),
    )
    assert context == ""


def test_network_failure_and_unsupported_harness_leave_session_usable():
    event = HookEvent(kind="session_start", session_id="run1", cwd="/repo")
    assert (
        released_instruction_context(
            DeliveryClient(error=TimeoutError()), {"client": "codex_cli"}, event
        )
        == ""
    )
    client = DeliveryClient([delivery()])
    assert released_instruction_context(client, {"client": "cursor"}, event) == ""
    assert client.calls == []


@pytest.mark.parametrize(
    ("agent", "client_name"), [("codex", "codex_cli"), ("claude", "claude_code")]
)
def test_session_start_places_release_in_native_additional_context(
    agent, client_name, tmp_path, monkeypatch, capsys
):
    scripts = Path(__file__).resolve().parents[1] / f"{agent}-plugin/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    monkeypatch.setenv("STASH_CODEX_DATA", str(tmp_path))
    modules = ("adapt", "config", "on_session_start")
    for name in modules:
        sys.modules.pop(name, None)
    try:
        mod = importlib.import_module("on_session_start")
        item = delivery()
        client = DeliveryClient([item])
        cfg = {
            "client": client_name,
            "agent_name": "test",
            "api_key": "test",
            "api_endpoint": "https://example.test",
        }
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
        monkeypatch.setattr(mod, "get_stdin_data", lambda: {"session_id": "run1", "cwd": "/repo"})
        monkeypatch.setattr(mod, "get_config", lambda: cfg)
        monkeypatch.setattr(mod, "uploads_enabled", lambda c: True)
        monkeypatch.setattr(mod, "spawn_skills_sync", lambda c: None)
        monkeypatch.setattr(mod, "spawn_session_watcher", lambda **k: None)

        def create_session(_client, _cfg, state, _event, _directory):
            state["session_row_id"] = str(uuid4())
            return "https://example.test/session"

        monkeypatch.setattr(mod, "create_session_record", create_session)
        monkeypatch.setattr(sys.modules["config"], "get_client", lambda: nullcontext(client))
        if agent == "codex":
            monkeypatch.setattr(mod, "get_client", lambda: nullcontext(client))
            monkeypatch.setattr(mod, "_auto_update_message", lambda: "Existing warning")
        else:
            monkeypatch.setattr(mod, "shadow_install_warning", lambda: None)
            monkeypatch.setattr(mod, "skills_update_notice", lambda: None)
            monkeypatch.setattr(mod, "upload_health_warning", lambda *a: None)
        mod.main()
        result = json.loads(capsys.readouterr().out)
        assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert instruction_context(item) in result["hookSpecificOutput"]["additionalContext"]
        if agent == "codex":
            assert result["systemMessage"] == "Existing warning"
        assert client.calls == [("run1", "codex" if agent == "codex" else "claude_code", "/repo")]
    finally:
        for name in modules:
            sys.modules.pop(name, None)
