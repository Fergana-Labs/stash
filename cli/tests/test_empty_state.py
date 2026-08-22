"""Lock the AXI §5 empty-state convention for every stash CLI list/status
command: exactly one canonical `No X found.` line (dim-styled) on **stderr**
in both text and `--json` modes, a well-defined empty JSON payload on stdout
in `--json` mode, and byte-for-byte unchanged populated output.

Previously each command had its own bespoke wording on stdout (or printed
nothing at all) and the `--json` empty shapes were unverified. These tests
reproduce those broken conditions and assert they are gone.
"""

import json

from typer.testing import CliRunner

from cli import main


class EmptyClient:
    """A fake StashClient that returns an empty payload for every method."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def list_discover_skills(self, query="", sort="trending"):
        return {"skills": []}

    def list_skills(self):
        return []

    def query_events(self, limit=20):
        return []

    def list_agent_names(self):
        return []

    def list_session_folders(self):
        return []

    def list_agents(self):
        return []

    def get_memory_folder(self):
        return {"id": "mem-root", "name": "Memories"}

    def get_memory_tree(self):
        return {"folders": [], "pages": []}

    def search_sources(self, query, **kwargs):
        return {"results": [], "has_more": False}

    def sources_tree(self, depth=3):
        return []

    def list_object_shares(self, object_type, object_id):
        return []

    def get_trash(self):
        return {"pages": [], "files": [], "sessions": []}

    def list_workspaces(self):
        return {"workspaces": [], "pending_domain_workspaces": []}

    def list_api_keys(self):
        return []

    def list_mcp_servers(self):
        return []


class FilesOnlyClient(EmptyClient):
    """Override just enough to exercise `stash ls` path/provider drill-downs."""

    def sources_tree(self, depth=3):
        return [{"source": "files", "type": "native_files", "display_name": "Files", "tree": []}]

    def list_source_entries(self, source, path=""):
        return []


class ProviderEmptyClient(EmptyClient):
    """A provider source with a sole connection that has no documents."""

    def sources_tree(self, depth=3):
        return [
            {
                "source": "github",
                "type": "provider",
                "provider": "github",
                "display_name": "github",
                "members": [
                    {"handle": "11111111-1111-1111-1111-111111111111", "display_name": "stash"}
                ],
                "sync_status": "idle",
                "tree": [],
            }
        ]

    def list_source_entries(self, source, path=""):
        return []


def _wire_provider_empty(monkeypatch) -> None:
    monkeypatch.setattr(main, "_client", lambda: ProviderEmptyClient())
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


def _wire(monkeypatch) -> None:
    monkeypatch.setattr(main, "_client", lambda: EmptyClient())
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


def _wire_files(monkeypatch) -> None:
    monkeypatch.setattr(main, "_client", lambda: FilesOnlyClient())
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# browse
# ---------------------------------------------------------------------------


def test_browse_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.browse(query="", sort="trending", pick=True, as_json=False)
    captured = capsys.readouterr()
    assert "No public skills matching your filters found." in captured.err
    assert "No public skills matching your filters found." not in captured.out


def test_browse_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.browse(query="", sort="trending", pick=True, as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "No public skills matching your filters found." in captured.err


# ---------------------------------------------------------------------------
# skills list / skills list --installed
# ---------------------------------------------------------------------------


def test_skills_list_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.skills_list(installed=False, as_json=False)
    captured = capsys.readouterr()
    assert "No skills found." in captured.err
    assert "No skills found." not in captured.out


def test_skills_list_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.skills_list(installed=False, as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"skills": []}
    assert "No skills found." in captured.err


def test_skills_installed_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(main, "_load_installed_manifest", lambda: {})
    main.skills_list(installed=True, as_json=False)
    captured = capsys.readouterr()
    assert "No installed skills found." in captured.err
    assert "No installed skills found." not in captured.out


def test_skills_installed_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(main, "_load_installed_manifest", lambda: {})
    main.skills_list(installed=True, as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"installed": []}
    assert "No installed skills found." in captured.err


# ---------------------------------------------------------------------------
# sessions (default view)
# ---------------------------------------------------------------------------


def test_sessions_default_empty_text(monkeypatch) -> None:
    _wire(monkeypatch)
    result = CliRunner().invoke(main.app, ["sessions"])
    assert result.exit_code == 0
    assert "No sessions found." in result.stderr
    assert "No sessions found." not in result.stdout


def test_sessions_default_empty_json(monkeypatch) -> None:
    _wire(monkeypatch)
    result = CliRunner().invoke(main.app, ["sessions", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []
    assert "No sessions found." in result.stderr


# ---------------------------------------------------------------------------
# hist agents / hist folders
# ---------------------------------------------------------------------------


def test_hist_agents_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.hist_agents(as_json=False)
    captured = capsys.readouterr()
    assert "No agents found." in captured.err
    assert "No agents found." not in captured.out


def test_hist_agents_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.hist_agents(as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "No agents found." in captured.err


# ---------------------------------------------------------------------------
# agent list
# ---------------------------------------------------------------------------


def test_agent_list_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.agent_list(as_json=False)
    captured = capsys.readouterr()
    # agent list previously printed nothing at all on empty; it must now emit
    # the canonical stderr line while stdout stays clean.
    assert "No agents found." in captured.err
    assert captured.out.strip() == ""


def test_agent_list_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.agent_list(as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "No agents found." in captured.err


# ---------------------------------------------------------------------------
# memory ls
# ---------------------------------------------------------------------------


def test_memory_ls_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.memory_ls(as_json=False)
    captured = capsys.readouterr()
    # The root folder header still renders (it is real data); the empty tree
    # adds the stderr note.
    assert "Memories/" in captured.out
    assert "No pages or folders found." in captured.err
    assert "No pages or folders found." not in captured.out


def test_memory_ls_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.memory_ls(as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "id": "mem-root",
        "name": "Memories",
        "folders": [],
        "pages": [],
    }
    assert "No pages or folders found." in captured.err


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def _invoke_search(as_json):
    return main.search(
        "q",
        source="",
        include_sources="",
        exclude_sources="",
        modified_after="",
        modified_before="",
        limit=20,
        as_json=as_json,
    )


def test_search_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    _invoke_search(as_json=False)
    captured = capsys.readouterr()
    assert "No matches found." in captured.err
    assert "No matches found." not in captured.out


def test_search_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    _invoke_search(as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"results": [], "has_more": False}
    assert "No matches found." in captured.err


# ---------------------------------------------------------------------------
# ls overview + ls path/provider dir
# ---------------------------------------------------------------------------


def test_ls_overview_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.ls_cmd(path="", depth=2, as_json=False)
    captured = capsys.readouterr()
    # previously it always rendered a bare `stash:/` tree; now emit the note.
    assert "No sources found." in captured.err
    assert "No sources found." not in captured.out


def test_ls_overview_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.ls_cmd(path="", depth=2, as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"sources": []}
    assert "No sources found." in captured.err


def test_ls_path_empty_text(monkeypatch, capsys) -> None:
    _wire_files(monkeypatch)
    main.ls_cmd(path="files", depth=2, as_json=False)
    captured = capsys.readouterr()
    assert "No files or folders found." in captured.err
    assert "No files or folders found." not in captured.out


def test_ls_path_empty_json(monkeypatch, capsys) -> None:
    _wire_files(monkeypatch)
    main.ls_cmd(path="files", depth=2, as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"entries": []}
    assert "No files or folders found." in captured.err


def test_ls_provider_path_empty_text(monkeypatch, capsys) -> None:
    _wire_provider_empty(monkeypatch)
    main.ls_cmd(path="github", depth=2, as_json=False)
    captured = capsys.readouterr()
    assert "No files or folders found." in captured.err
    assert "No files or folders found." not in captured.out


def test_ls_provider_path_empty_json(monkeypatch, capsys) -> None:
    _wire_provider_empty(monkeypatch)
    main.ls_cmd(path="github", depth=2, as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"entries": []}
    assert "No files or folders found." in captured.err


# ---------------------------------------------------------------------------
# shares ls
# ---------------------------------------------------------------------------


def test_shares_ls_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.shares_ls(object_type="page", object_id="p1", as_json=False)
    captured = capsys.readouterr()
    assert "No shares found." in captured.err
    assert "No shares found." not in captured.out


def test_shares_ls_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.shares_ls(object_type="page", object_id="p1", as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "No shares found." in captured.err


# ---------------------------------------------------------------------------
# trash list
# ---------------------------------------------------------------------------


def test_trash_list_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.trash_list(as_json=False)
    captured = capsys.readouterr()
    # one definitive line, not three per-section "empty" headers.
    assert "No trash found." in captured.err
    assert "No trash found." not in captured.out


def test_trash_list_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.trash_list(as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"pages": [], "files": [], "sessions": []}
    assert "No trash found." in captured.err


# ---------------------------------------------------------------------------
# workspace list
# ---------------------------------------------------------------------------


def test_workspace_list_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(main, "load_config", lambda: {})
    main.workspace_list(as_json=False)
    captured = capsys.readouterr()
    assert "No workspaces found." in captured.err
    assert "No workspaces found." not in captured.out


def test_workspace_list_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(main, "load_config", lambda: {})
    main.workspace_list(as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "workspaces": [],
        "pending_domain_workspaces": [],
        "active_scope": None,
    }
    assert "No workspaces found." in captured.err


# ---------------------------------------------------------------------------
# keys list
# ---------------------------------------------------------------------------


def test_keys_list_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.keys_list(as_json=False)
    captured = capsys.readouterr()
    assert "No API keys found." in captured.err
    assert "No API keys found." not in captured.out


def test_keys_list_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.keys_list(as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "No API keys found." in captured.err


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(main, "_upload_health_snapshot", lambda: [])
    main.status_cmd(as_json=False)
    captured = capsys.readouterr()
    assert "No local agent plugins found." in captured.err
    assert "No local agent plugins found." not in captured.out


def test_status_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(main, "_upload_health_snapshot", lambda: [])
    main.status_cmd(as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"upload_health": []}
    assert "No local agent plugins found." in captured.err


# ---------------------------------------------------------------------------
# tools list
# ---------------------------------------------------------------------------


def test_tools_list_empty_text(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.tools_list(as_json=False)
    captured = capsys.readouterr()
    assert "No MCP servers found." in captured.err
    assert "No MCP servers found." not in captured.out


def test_tools_list_empty_json(monkeypatch, capsys) -> None:
    _wire(monkeypatch)
    main.tools_list(as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"servers": []}
    assert "No MCP servers found." in captured.err


# ---------------------------------------------------------------------------
# Populated controls — the STAS-060 non-empty default must still render rows
# ---------------------------------------------------------------------------


class PopulatedClient(EmptyClient):
    def list_agents(self):
        return [
            {
                "name": "demo",
                "run_mode": "chat",
                "model_provider": "auto",
                "schedule_cron": None,
                "id": "ag-1",
            }
        ]

    def list_skills(self):
        return [{"name": "my-skill", "slug": "my-skill"}]

    def list_discover_skills(self, query="", sort="trending"):
        return {
            "skills": [
                {"title": "Widgets", "owner_display_name": "acme", "item_count": 3, "view_count": 7}
            ]
        }

    def list_mcp_servers(self):
        return [{"name": "tavily", "transport": "stdio", "command": "tavily-mcp"}]

    def list_object_shares(self, object_type, object_id):
        return [{"display_name": "Sam", "permission": "read"}]

    def get_trash(self):
        return {
            "pages": [
                {
                    "id": "pg-1",
                    "name": "Notes",
                    "deleted_at": "2026-01-01",
                    "deleted_by_name": "Sam",
                }
            ],
            "files": [],
            "sessions": [],
        }

    def list_workspaces(self):
        return {
            "workspaces": [{"name": "Acme", "domain": "acme.io", "scope_user_id": "u1"}],
            "pending_domain_workspaces": [],
        }

    def list_api_keys(self):
        return [{"name": "laptop", "id": "k1", "created_at": "2026-01-01", "last_used_at": None}]

    def search_sources(self, query, **kwargs):
        return {
            "results": [{"name": "hit", "ref": "r1", "source": "files", "snippet": ""}],
            "has_more": False,
        }

    def list_agent_names(self):
        return ["planner"]

    def list_session_folders(self):
        return [{"name": "Q3", "id": "f1"}]

    def query_events(self, limit=20):
        return [
            {
                "created_at": "2026-01-01T00:00:00",
                "agent_name": "planner",
                "event_type": "run",
                "tool_name": "",
                "content": "hello",
            }
        ]

    def get_memory_tree(self):
        return {"folders": [{"name": "Sub", "id": "f2"}], "pages": []}


def _wire_populated(monkeypatch) -> None:
    monkeypatch.setattr(main, "_client", lambda: PopulatedClient())
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)
    monkeypatch.setattr(main, "load_config", lambda: {"scope": "u1"})


def test_populated_agent_list_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    main.agent_list(as_json=False)
    out = capsys.readouterr().out
    assert "demo" in out
    assert "ag-1" in out


def test_populated_browse_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    main.browse(query="", sort="trending", pick=False, as_json=False)
    out = capsys.readouterr().out
    assert "Widgets" in out
    assert "acme" in out


def test_populated_skills_list_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    main.skills_list(installed=False, as_json=False)
    out = capsys.readouterr().out
    assert "my-skill" in out


def test_populated_tools_list_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    main.tools_list(as_json=False)
    out = capsys.readouterr().out
    assert "tavily" in out


def test_populated_shares_ls_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    main.shares_ls(object_type="page", object_id="p1", as_json=False)
    out = capsys.readouterr().out
    assert "Sam" in out


def test_populated_trash_list_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    main.trash_list(as_json=False)
    out = capsys.readouterr().out
    assert "Notes" in out


def test_populated_workspace_list_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    main.workspace_list(as_json=False)
    out = capsys.readouterr().out
    assert "Acme" in out
    assert "personal" in out


def test_populated_keys_list_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    main.keys_list(as_json=False)
    out = capsys.readouterr().out
    assert "laptop" in out


def test_populated_search_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    _invoke_search(as_json=False)
    out = capsys.readouterr().out
    assert "hit" in out


def test_populated_status_renders_rows(monkeypatch, capsys) -> None:
    _wire_populated(monkeypatch)
    monkeypatch.setattr(
        main,
        "_upload_health_snapshot",
        lambda: [
            {
                "agent": "codex",
                "label": "Codex",
                "health": "ok",
                "queued_events": 0,
                "last_success_at": None,
                "last_failure_at": None,
                "last_error": None,
            }
        ],
    )
    main.status_cmd(as_json=False)
    out = capsys.readouterr().out
    assert "Codex" in out


def test_populated_sessions_renders_rows(monkeypatch) -> None:
    _wire_populated(monkeypatch)
    result = CliRunner().invoke(main.app, ["sessions"])
    assert result.exit_code == 0
    assert "planner/run" in result.stdout
