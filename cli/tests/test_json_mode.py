"""STAS-060 — universal JSON mode for every stash CLI command.

Assert the data-channel invariant that defines JSON mode:
  * ``stash --json <cmd>`` and ``stash <cmd> --json`` behave identically;
  * stdout carries exactly one machine-parseable JSON document and nothing else;
  * every progress/status/warning/error goes to stderr, never stdout;
  * error paths still exit with the STAS-058 classified codes (0/1/2) and
    never write error text to stdout;
  * default (non-JSON) Rich table/text output is unchanged.

Tests grow across Steps 1-5. Step 1 covers the universal runtime flag:
the root-callback ``--json`` option must set a module flag that ORs into
``_use_json`` so the flag works from either invocation position.
"""

import json

import pytest
from typer.testing import CliRunner

from cli import main

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_json_mode():
    # Each Typer invocation is a fresh CLI process in production, so the
    # module-level JSON-mode flag starts False. Reset it per test so in-process
    # CliRunner invocations do not leak state across tests.
    main._JSON_MODE = False
    yield
    main._JSON_MODE = False


SOURCES = [
    {
        "source": "files",
        "type": "native_files",
        "display_name": "Files",
        "tree": [],
    }
]


class FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def sources_tree(self, depth=3):
        return SOURCES


def _setup(monkeypatch):
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: FakeClient())
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Step 1 — universal runtime flag, both flag positions
# ---------------------------------------------------------------------------


def test_global_json_flag_matches_per_command_flag(monkeypatch):
    _setup(monkeypatch)

    global_result = runner.invoke(main.app, ["--json", "ls"])
    per_command_result = runner.invoke(main.app, ["ls", "--json"])

    assert global_result.exit_code == 0
    assert per_command_result.exit_code == 0
    # Both positions produce identical parseable JSON on stdout.
    assert json.loads(global_result.stdout) == json.loads(per_command_result.stdout)
    assert json.loads(global_result.stdout) is not None


def test_json_mode_stdout_is_pure_json(monkeypatch):
    _setup(monkeypatch)

    result = runner.invoke(main.app, ["--json", "ls"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, (list, dict))


def test_global_json_flag_is_reset_between_invocations(monkeypatch):
    _setup(monkeypatch)

    # A prior `--json` invocation must not leak JSON mode into a later one:
    # each CLI run is its own process starting with the flag False.
    runner.invoke(main.app, ["--json", "ls"])
    main._JSON_MODE = False  # fresh process boundary
    result = runner.invoke(main.app, ["ls"])

    assert result.exit_code == 0
    # Default output is Rich text, not JSON.
    assert not result.stdout.lstrip().startswith("{")
    assert not result.stdout.lstrip().startswith("[")


def test_help_version_and_bare_invoke_never_emit_json(monkeypatch):
    _setup(monkeypatch)
    monkeypatch.setattr(main, "__version__", "9.9.9")

    help_result = runner.invoke(main.app, ["--json", "--help"])
    version_result = runner.invoke(main.app, ["--json", "-v"])
    bare_result = runner.invoke(main.app, ["--json"])

    assert help_result.exit_code == 0
    assert version_result.exit_code == 0
    assert bare_result.exit_code == 0
    # Help/version/no-subcommand never emit a JSON document even with --json.
    assert "stash 9.9.9" in version_result.stdout
    assert not help_result.stdout.lstrip().startswith("{")
    assert not help_result.stdout.lstrip().startswith("[")
    assert not version_result.stdout.lstrip().startswith("{")
    assert not bare_result.stdout.lstrip().startswith("{")
    assert not bare_result.stdout.lstrip().startswith("[")


def test_use_json_or_semantics():
    # Per-command flag alone.
    assert main._use_json(True) is True
    # Neither flag set.
    assert main._use_json(False) is False
    # Global flag set after `--json` makes the per-command flag moot.
    main._JSON_MODE = True
    try:
        assert main._use_json(False) is True
        assert main._use_json(True) is True
    finally:
        main._JSON_MODE = False


# ---------------------------------------------------------------------------
# Step 2 — app-group commands swept onto the JSON flag
# ---------------------------------------------------------------------------


class ActionClient:
    """FakeClient with the client methods the swept app-group commands call."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def delete_page(self, i):
        return None

    def purge_page(self, i):
        return None

    def restore_page(self, i):
        return None

    def batch_move(self, others, target_folder_id=None, move_to_root=False):
        return None

    def assign_session_folder(self, session_id, folder_id=None):
        return None

    def copy_page(self, i, target_folder_id=None):
        return {"id": f"copy-{i}", "name": f"Copy of {i}"}

    def resend_verification_email(self):
        return {"sent_to": "you@example.com"}


def _setup_action(monkeypatch):
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: ActionClient())
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


def test_rm_json_emits_result_object(monkeypatch):
    _setup_action(monkeypatch)
    result = runner.invoke(main.app, ["rm", "page:p1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["items"] == 1
    assert payload["action"] == "moved to trash"


def test_rm_json_trash_vs_permanent(monkeypatch):
    _setup_action(monkeypatch)
    result = runner.invoke(main.app, ["rm", "page:p1", "--permanent", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "permanently deleted"
    assert payload["permanent"] is True


def test_restore_json_emits_result_object(monkeypatch):
    _setup_action(monkeypatch)
    result = runner.invoke(main.app, ["restore", "page:p1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["items"] == 1


def test_mv_json_emits_result_object(monkeypatch):
    _setup_action(monkeypatch)
    result = runner.invoke(main.app, ["mv", "page:p1", "--to-folder", "f1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["items"] == 1


def test_cp_json_emits_copies(monkeypatch):
    _setup_action(monkeypatch)
    result = runner.invoke(main.app, ["cp", "page:p1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["copies"][0]["id"] == "copy-p1"


def test_start_json_emits_result_and_streaming_unchanged(monkeypatch):
    _setup_action(monkeypatch)
    captured = {"called": False}

    def fake_start():
        captured["called"] = True

    monkeypatch.setattr(main, "start_streaming", fake_start)
    result = runner.invoke(main.app, ["start", "--json"])
    assert result.exit_code == 0
    assert captured["called"] is True
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["streaming"] is True


def test_stop_json_emits_result(monkeypatch):
    _setup_action(monkeypatch)
    captured = {"called": False}

    def fake_stop():
        captured["called"] = True

    monkeypatch.setattr(main, "stop_streaming", fake_stop)
    result = runner.invoke(main.app, ["stop", "--json"])
    assert result.exit_code == 0
    assert captured["called"] is True
    payload = json.loads(result.stdout)
    assert payload["streaming"] is False


def test_verify_email_json_emits_sent_to(monkeypatch):
    _setup_action(monkeypatch)
    result = runner.invoke(main.app, ["verify-email", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["sent_to"] == "you@example.com"


class _FakeUpgradeResult:
    returncode = 0


def test_upgrade_json_emits_result_object(monkeypatch):
    import subprocess

    monkeypatch.setattr("stashai.release.is_editable", lambda: False)
    monkeypatch.setattr(
        "stashai.release.upgrade_command", lambda: ["uv", "tool", "install", "stashai"]
    )
    monkeypatch.setattr(subprocess, "run", lambda cmd: _FakeUpgradeResult())
    result = runner.invoke(main.app, ["upgrade", "--json"])
    assert result.exit_code == 0
    # stdout is exactly one parseable JSON document; progress text stays on
    # stderr, never on stdout.
    assert json.loads(result.stdout) == {"ok": True, "exit_code": 0}
    assert "Upgrading stashai" in result.stderr
    assert "Upgrading stashai" not in result.stdout
    # Parity: the global flag behaves identically.
    result = runner.invoke(main.app, ["--json", "upgrade"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"ok": True, "exit_code": 0}


def test_delete_json_stdout_has_no_human_text(monkeypatch):
    _setup_action(monkeypatch)
    result = runner.invoke(main.app, ["rm", "page:p1", "--json"])
    assert result.exit_code == 0
    # The default-mode human summary line never leaks onto stdout in JSON mode.
    assert "item(s)" not in result.stdout
    # stdout is exactly one parseable JSON document.
    assert json.loads(result.stdout)["ok"] is True
    assert result.stderr == ""


def test_default_output_unchanged_for_start(monkeypatch):
    _setup_action(monkeypatch)
    monkeypatch.setattr(main, "start_streaming", lambda: None)
    result = runner.invoke(main.app, ["start"])
    assert result.exit_code == 0
    assert "Streaming enabled." in result.stdout
    assert not result.stdout.lstrip().startswith("{")


# ---------------------------------------------------------------------------
# Step 3 — sub-app command groups swept onto the JSON flag
# ---------------------------------------------------------------------------


class SubAppClient:
    """FakeClient covering the client methods the swept sub-app commands call."""

    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    # skills_app
    def create_folder(self, name):
        self.calls.append(("create_folder", name))
        return {"id": "folder-1"}

    def create_page(self, **kw):
        self.calls.append(("create_page", kw))
        return {"id": "page-1"}

    def convert_folder_to_skill(self, folder_id):
        self.calls.append(("convert_folder_to_skill", folder_id))
        return None

    def unpublish_skill(self, skill_id):
        self.calls.append(("unpublish_skill", skill_id))

    # files_app
    def get_page(self, page_id):
        return {"id": page_id, "name": "Page", "content": "Hi"}

    def get_file_text(self, file_id):
        return {"status": "done", "text": "extracted text", "error": None}

    def get_file(self, file_id):
        self.calls.append(("get_file", file_id))
        return {"id": file_id, "name": "report.pdf"}

    def download_file(self, file_id):
        self.calls.append(("download_file", file_id))
        return b"pdf-bytes"

    # hist_app
    def list_session_folders(self):
        return [{"name": "Launch", "id": "f1"}]

    def create_session_folder(self, name):
        self.calls.append(("create_session_folder", name))
        return {"id": "f-new", "name": name}

    # agent_app (SSE streams)
    def resolve_session(self, ref, trashed=False):
        # Session handles resolve server-side; these tests pass ids through.
        return {"matched": False, "session_id": ref, "id": ref, "name": None}

    def list_agents(self):
        return [
            {"id": "ag-1", "name": "Default", "run_mode": "chat", "model_provider": None},
            {"id": "ag-2", "name": "Reporter", "run_mode": "scheduled", "model_provider": None},
        ]

    def agent_chat_events(self, message, session_id=None, agent_id=None):
        self.calls.append(("chat", message, session_id, agent_id))
        yield {"type": "session", "session_id": "agent-abc"}
        yield {"type": "text", "delta": "hello "}
        yield {"type": "text", "delta": "world"}
        yield {"type": "end"}

    def agent_run_events(self, agent_id):
        self.calls.append(("run", agent_id))
        yield {"type": "text", "delta": "ran"}
        yield {"type": "end"}

    def agent_turn_status(self, session_id):
        return {"session_id": session_id, "running": False}

    def get_agent_chat(self, session_id):
        return {
            "session_id": session_id,
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "done"},
            ],
        }

    def stop_agent_turn(self, session_id):
        self.calls.append(("stop_app", session_id))

    # sources / shares
    def delete_source(self, source_id):
        self.calls.append(("delete_source", source_id))

    def unshare_object(self, object_type, object_id, principal_type, principal_id):
        self.calls.append(("unshare_object", object_type, object_id))

    # tables
    def delete_table_row(self, table_id, row_id):
        self.calls.append(("delete_table_row", table_id, row_id))

    def delete_table(self, table_id):
        self.calls.append(("delete_table", table_id))

    def _request(self, method, url, params=None):
        self.calls.append(("table_export_request", url))
        resp = type("R", (), {})()
        resp.text = "name,age\namy,30\n"
        return resp

    def get_table(self, table_id):
        return {"id": table_id, "columns": []}

    # keys / tools
    def revoke_api_key(self, key_id):
        self.calls.append(("revoke_api_key", key_id))

    def list_mcp_servers(self):
        return [
            {"id": "srv-1", "name": "linear", "transport": "stdio", "command": "npx linear-mcp"}
        ]

    def delete_mcp_server(self, server_id):
        self.calls.append(("delete_mcp_server", server_id))


def _setup_subapp(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: SubAppClient(calls))
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)
    return calls


def _assert_pure_json(result):
    """stdout is exactly one parseable JSON document, no human text."""
    assert result.exit_code == 0
    assert json.loads(result.stdout) is not None
    # A trailing human line (e.g. a Rich summary) would make json.loads fail,
    # so a successful parse already asserts the clean-stdout invariant.


# --- skills_app ---


def test_skills_add_json_emits_result_object(monkeypatch, tmp_path):
    calls = _setup_subapp(monkeypatch)
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# S")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(main.app, ["skills", "add", str(skill_dir), "--json"])
    assert result.exit_code == 0
    assert ("convert_folder_to_skill", "folder-1") in calls
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["folder_id"] == "folder-1"
    assert payload["name"] == "my-skill"


def test_skills_unpublish_json(monkeypatch):
    calls = _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["skills", "unpublish", "skill-9", "--json"])
    assert result.exit_code == 0
    assert ("unpublish_skill", "skill-9") in calls
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["skill_id"] == "skill-9"


def test_skills_add_default_output_unchanged(monkeypatch, tmp_path):
    _setup_subapp(monkeypatch)
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# S")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(main.app, ["skills", "add", str(skill_dir)])
    assert result.exit_code == 0
    assert "Added skill" in result.stdout
    assert not result.stdout.lstrip().startswith("{")


# --- files_app ---


def test_files_read_page_json(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["files", "read-page", "p1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "p1"
    assert payload["name"] == "Page"


def test_files_text_json_emits_structured_payload(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["files", "text", "f1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["text"] == "extracted text"
    assert payload["file_id"] == "f1"


def test_files_text_default_output_is_raw_text(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["files", "text", "f1"])
    assert result.exit_code == 0
    assert "extracted text\n" == result.stdout


def test_files_download_json(monkeypatch, tmp_path):
    calls = _setup_subapp(monkeypatch)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(main.app, ["files", "download", "f1", "--json"])
    assert result.exit_code == 0
    assert ("download_file", "f1") in calls
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["bytes"] == 9
    assert payload["name"] == "report.pdf"


# --- agent_app (interactive/streaming) ---


def test_agent_chat_json_streams_single_result(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["agent", "chat", "hi", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session_id"] == "agent-abc"
    assert payload["text"] == "hello world"


def test_agent_run_json_emits_result(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["agent", "run", "Reporter", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session_id"] is None
    assert payload["text"] == "ran"


def test_agent_watch_json_collects_messages_and_no_human_stdout(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["agent", "watch", "agent-abc", "--poll", "0", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session_id"] == "agent-abc"
    assert [m["content"] for m in payload["messages"]] == ["hi", "done"]
    assert "Turn finished" not in result.stdout


def test_agent_stop_json(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["agent", "stop", "agent-abc", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["session_id"] == "agent-abc"


def test_agent_chat_json_nowhere_requires_a_tty(monkeypatch):
    # The SSE stream must run identically headless: JSON on stdout, no Rich UI.
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["--json", "agent", "chat", "hi"], env={"TERM": "dumb"})
    assert result.exit_code == 0
    assert json.loads(result.stdout)["text"] == "hello world"


# --- sources / shares ---


def test_sources_rm_json(monkeypatch):
    calls = _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["sources", "rm", "src-1", "--json"])
    assert result.exit_code == 0
    assert ("delete_source", "src-1") in calls
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["source_id"] == "src-1"


def test_shares_rm_json(monkeypatch):
    calls = _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["shares", "rm", "page", "obj-1", "u-9", "--json"])
    assert result.exit_code == 0
    assert ("unshare_object", "page", "obj-1") in calls
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["object_id"] == "obj-1"


# --- tables ---


def test_tables_delete_row_json(monkeypatch):
    calls = _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["tables", "delete-row", "t-1", "r-1", "--json"])
    assert result.exit_code == 0
    assert ("delete_table_row", "t-1", "r-1") in calls
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["row_id"] == "r-1"


def test_tables_delete_json_skips_interactive_confirm(monkeypatch):
    calls = _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["tables", "delete", "t-1", "--json"])
    assert result.exit_code == 0
    assert ("delete_table", "t-1") in calls
    assert json.loads(result.stdout)["ok"] is True


def test_tables_export_json_emits_csv_payload(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["tables", "export", "t-1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["table_id"] == "t-1"
    assert payload["csv"] == "name,age\namy,30\n"


def test_tables_export_default_dumps_raw_csv(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["tables", "export", "t-1"])
    assert result.exit_code == 0
    assert result.stdout == "name,age\namy,30\n"


# --- workspace / keys / prompts ---


def test_workspace_switch_json_personal(monkeypatch):
    _setup_subapp(monkeypatch)
    monkeypatch.setattr(main, "save_scope", lambda v: None)
    result = runner.invoke(main.app, ["workspace", "switch", "personal", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["workspace"] == "personal"


def test_keys_revoke_json(monkeypatch):
    calls = _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["keys", "revoke", "key-1", "--json"])
    assert result.exit_code == 0
    assert ("revoke_api_key", "key-1") in calls
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["key_id"] == "key-1"


def test_prompts_agent_guidance_json(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["prompts", "agent-guidance", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "A Skill is a special folder" in payload["prompt"]


def test_prompts_agent_guidance_default_is_plain_text(monkeypatch):
    _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["prompts", "agent-guidance"])
    assert result.exit_code == 0
    assert "A Skill is a special folder" in result.stdout
    assert not result.stdout.lstrip().startswith("{")


# --- tools ---


def test_tools_remove_json(monkeypatch):
    calls = _setup_subapp(monkeypatch)
    result = runner.invoke(main.app, ["tools", "remove", "linear", "--json"])
    assert result.exit_code == 0
    assert ("delete_mcp_server", "srv-1") in calls
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["name"] == "linear"


def test_tools_install_json(monkeypatch, tmp_path):
    _setup_subapp(monkeypatch)
    monkeypatch.setattr(main, "_merge_mcp_server", lambda dest, name, entry: "installed")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(main.app, ["tools", "install", "linear", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["name"] == "linear"
    assert payload["status"] == "installed"


# --- hook_app ---


def test_hook_auto_update_json(monkeypatch):
    _setup_subapp(monkeypatch)
    monkeypatch.setattr(main, "set_codex_auto_update", lambda v: None)
    result = runner.invoke(main.app, ["hook", "auto-update", "on", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["autoupdate"] is True
    assert payload["choice"] == "on"


def test_hook_auto_update_default_unchanged(monkeypatch):
    _setup_subapp(monkeypatch)
    monkeypatch.setattr(main, "set_codex_auto_update", lambda v: None)
    result = runner.invoke(main.app, ["hook", "auto-update", "on"])
    assert result.exit_code == 0
    assert "Codex auto-update on." in result.stdout
    assert not result.stdout.lstrip().startswith("{")


# ---------------------------------------------------------------------------
# Step 4 — clean-stdout invariant + minimal JSON schema
# ---------------------------------------------------------------------------


class _LsClient:
    """FakeClient whose sources_tree always yields the overview list, letting
    the test drive empty/single/populated states via monkeypatch."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def sources_tree(self, depth=3):
        return self._trees


def _setup_ls(monkeypatch, trees):
    client = _LsClient()
    client._trees = trees
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: client)
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


def _assert_scalar_values(node, path="root"):
    """Recursively assert the minimal JSON schema bound in output_json: every
    value serializes to a scalar (str/number/bool/null) via default=str, and
    dict keys are plain strings (never Python objects that would str() into a
    mixed-case key)."""
    if isinstance(node, dict):
        for key, value in node.items():
            assert isinstance(key, str), f"non-string key {key!r} at {path}"
            _assert_scalar_values(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _assert_scalar_values(item, f"{path}[{i}]")
    else:
        assert node is None or isinstance(node, (str, int, float, bool)), (
            f"non-scalar value {node!r} at {path}"
        )


def test_ls_json_empty_undefined_and_populated(monkeypatch):
    empty = []
    single = [{"source": "files", "type": "native_files", "display_name": "Files", "tree": []}]
    populated = [
        {"source": "files", "type": "native_files", "display_name": "Files", "tree": []},
        {
            "source": "github",
            "type": "provider",
            "provider": "github",
            "display_name": "github",
            "sync_status": "idle",
            "tree": [{"name": "docs", "kind": "folder", "children": []}],
        },
    ]
    for label, trees in (("empty", empty), ("single", single), ("populated", populated)):
        _setup_ls(monkeypatch, trees)
        result = runner.invoke(main.app, ["--json", "ls"])
        assert result.exit_code == 0, f"{label}: {result.output}"
        payload = json.loads(result.stdout)
        # The list-command JSON envelope is snake_case and always an object
        # with an array payload, even when the underlying data is empty.
        assert set(payload.keys()) == {"sources"}
        assert isinstance(payload["sources"], list)
        assert len(payload["sources"]) == len(trees)
        # The payload keys come from the backend as snake_case; every value must
        # be a scalar (the output_json default=str schema bound).
        for source in payload["sources"]:
            _assert_scalar_values(source)


def test_json_mode_error_goes_only_to_stderr(monkeypatch):
    """A forced 404 in `ls` must put the error on stderr (exit 1) and leave
    stdout empty — never interleave error text on the data channel."""
    from cli.client import StashError

    class _RaisingClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def sources_tree(self, depth=3):
            raise StashError(404, "folder not found")

    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: _RaisingClient())
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)

    result = runner.invoke(main.app, ["--json", "ls"])

    assert result.exit_code == 1  # 4xx -> EXIT_USER_ERROR
    assert result.stdout == ""  # no error text / partial JSON on stdout
    assert "folder not found" in result.stderr


def test_json_mode_internal_error_exits_two(monkeypatch):
    """A forced 5xx is not the caller's fault -> EXIT_INTERNAL_ERROR (2), still
    stderr-only."""
    from cli.client import StashError

    class _RaisingClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def sources_tree(self, depth=3):
            raise StashError(500, "upstream blew up")

    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: _RaisingClient())
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)

    result = runner.invoke(main.app, ["ls", "--json"])

    assert result.exit_code == 2  # 5xx -> EXIT_INTERNAL_ERROR
    assert result.stdout == ""
    assert "upstream blew up" in result.stderr


def test_global_json_flag_propagates_into_settings_and_browse(monkeypatch):
    """Commands that already declared --json must also honor the global
    `stash --json <cmd>` position, not just the per-command flag."""
    monkeypatch.setattr(main, "load_config", lambda: {"base_url": "https://api", "username": "u"})
    monkeypatch.setattr(main, "load_enabled_agents", lambda: ["claude", "codex"])
    monkeypatch.setattr(main, "session_link_enabled", lambda: True)
    monkeypatch.setattr(main, "PLUGIN_DATA_DIRS", {})
    monkeypatch.setattr(
        main,
        "_upload_health_snapshot",
        lambda: [{"agent": "claude", "health": "ok", "label": "Claude Code"}],
    )

    result = runner.invoke(main.app, ["--json", "settings"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["config"]["username"] == "u"
    assert payload["enabled_agents"] == ["claude", "codex"]
    assert payload["session_link"] is True
    assert payload["upload_health"][0]["agent"] == "claude"


def test_upload_json_routes_progress_to_stderr_only(monkeypatch, tmp_path):
    """Multi-file upload in JSON mode: progress/diagnostic lines go to stderr
    and stdout carries only the single result JSON document."""
    (tmp_path / "a.md").write_text("hello")
    (tmp_path / "b.txt").write_text("world")

    class _UploadClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create_folder(self, name):
            return {"id": "folder-1"}

        def create_page(self, name, **kw):
            return {"id": "page-1"}

        def upload_file(self, path):
            return {"id": "file-1", "name": "x"}

        def set_general_access(self, kind, obj_id, access):
            return None

        def convert_folder_to_skill(self, folder_id):
            return None

    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: _UploadClient())
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)
    monkeypatch.setattr(main, "_web_app_url", lambda: "https://app")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(main.app, ["upload", str(tmp_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)  # must parse: no human text interleaved
    assert isinstance(payload.get("folder"), dict)
    # Progress/status lines were routed to stderr, not stdout.
    assert "Uploading" in result.stderr or "Page:" in result.stderr or "File:" in result.stderr


# ---------------------------------------------------------------------------
# Code-review remediation: per-command --json must not leak status to stdout,
# and default (non-JSON) output stays byte-for-byte unchanged.
# ---------------------------------------------------------------------------


def test_connect_json_stdout_is_single_json_doc(monkeypatch, tmp_path):
    """`stash connect --json` must not leak the connect helper's status lines
    ("Wrote .stash" / "Appended Stash context to CLAUDE.md") onto stdout —
    stdout carries exactly one JSON document. The per-command flag is the case
    the old `_json_mode()`-only gate got wrong."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "load_config", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "start_streaming", lambda: None)
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)
    monkeypatch.setattr(main, "_git_toplevel", lambda *a: None)

    result = runner.invoke(main.app, ["connect", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)  # raises if human text leaked onto stdout
    assert payload == {"ok": True}
    # The helper status lines went to stderr, the only place they may land.
    assert "Wrote" in result.stderr
    assert "Appended Stash context" in result.stderr


def test_connect_json_global_and_after_are_identical(monkeypatch, tmp_path):
    """Both flag positions (`stash --json connect` and `stash connect --json`)
    produce identical stdout: exactly one JSON document, no status text."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "load_config", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "start_streaming", lambda: None)
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)
    monkeypatch.setattr(main, "_git_toplevel", lambda *a: None)

    global_res = runner.invoke(main.app, ["--json", "connect"])
    per_cmd_res = runner.invoke(main.app, ["connect", "--json"])

    assert global_res.exit_code == 0, global_res.output
    assert per_cmd_res.exit_code == 0, per_cmd_res.output
    assert json.loads(global_res.stdout) == json.loads(per_cmd_res.stdout) == {"ok": True}
    # No human/progress text on stdout in either position.
    assert global_res.stdout == per_cmd_res.stdout == '{"ok": true}\n'


def test_setup_json_connect_stdout_is_single_json_doc(monkeypatch, tmp_path):
    """`stash setup --json --no-record --connect` runs headless, auto-connects
    the repo, and still emits one parseable JSON result object on stdout with
    the connect helpers' status lines kept to stderr."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "load_config", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "stop_streaming", lambda: None)
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)
    monkeypatch.setattr(main, "_git_toplevel", lambda *a: None)

    result = runner.invoke(main.app, ["setup", "--json", "--no-record", "--connect"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)  # raises if human text leaked onto stdout
    assert payload["ok"] is True
    assert payload["connect"] is True
    assert "Wrote" in result.stderr
    assert "Appended Stash context" in result.stderr


def test_connect_default_output_keeps_status_on_stdout(monkeypatch, tmp_path):
    """Without --json, `stash connect` keeps the connect helper's status lines
    on stdout exactly as before — no byte-for-byte regression from gating."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "load_config", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "start_streaming", lambda: None)
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)
    monkeypatch.setattr(main, "_git_toplevel", lambda *a: None)

    result = runner.invoke(main.app, ["connect"])

    assert result.exit_code == 0, result.output
    assert "Wrote" in result.stdout
    assert "Appended Stash context" in result.stdout


def test_upload_default_keeps_progress_on_stdout(monkeypatch, tmp_path):
    """Multi-file upload without --json keeps its progress lines on stdout
    (Rich) — gating JSON mode must not silently move them to stderr."""
    (tmp_path / "a.md").write_text("hello")
    (tmp_path / "b.txt").write_text("world")

    class _UploadClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create_folder(self, name):
            return {"id": "folder-1"}

        def create_page(self, name, **kw):
            return {"id": "page-1"}

        def upload_file(self, path):
            return {"id": "file-1", "name": "x"}

        def set_general_access(self, kind, obj_id, access):
            return None

        def convert_folder_to_skill(self, folder_id):
            return None

    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: _UploadClient())
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)
    monkeypatch.setattr(main, "_web_app_url", lambda: "https://app")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(main.app, ["upload", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Uploading 2 file(s)" in result.stdout
    assert "Page:" in result.stdout
    # Default mode: progress lives on stdout, not stderr.
    assert "Uploading" not in result.stderr


def test_install_all_hooks_default_routes_checkmarks_to_stdout(monkeypatch, capsys):
    """`_install_all_hooks` without JSON mode prints the per-agent ✓ progress
    to stdout (Rich), exactly as before STAS-060 gated these lines."""
    monkeypatch.setattr(main, "_detected_agents", lambda: ["claude"])
    monkeypatch.setattr(
        main, "_INSTALLERS", {"claude": lambda force, use_json=False: ("installed", "v1.0")}
    )

    main._install_all_hooks(["claude"])

    captured = capsys.readouterr()
    assert "hook installed" in captured.out
    assert captured.err == ""


def test_install_all_hooks_json_routes_checkmarks_to_stderr(monkeypatch, capsys):
    """`_install_all_hooks` in JSON mode routes the per-agent ✓ progress to
    stderr, keeping stdout free of human text (STAS-060 contract)."""
    monkeypatch.setattr(main, "_detected_agents", lambda: ["claude"])
    monkeypatch.setattr(
        main, "_INSTALLERS", {"claude": lambda force, use_json=False: ("installed", "v1.0")}
    )

    main._install_all_hooks(["claude"], use_json=True)

    captured = capsys.readouterr()
    assert "hook installed" in captured.err
    assert captured.out == ""
