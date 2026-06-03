"""The `stash sources` sub-app + unified `stash search` are thin wrappers over
the client's VFS methods. These lock in the wiring: the right client method is
called with the source-optional arguments, so search-everything and
search-one-source both reach the server correctly."""

from cli import main


class _FakeClient:
    def __init__(self, calls: list):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def search_sources(self, workspace_id, query, source=None, limit=20):
        self._calls.append(("search", workspace_id, query, source, limit))
        return [{"source": "files", "ref": "p1", "name": "Runbook", "snippet": "deploy"}]

    def list_sources(self, workspace_id):
        self._calls.append(("list", workspace_id))
        return [
            {
                "source": "files",
                "type": "native_files",
                "capability": "navigable",
                "display_name": "Files",
            }
        ]

    def list_source_entries(self, workspace_id, source, path=""):
        self._calls.append(("entries", workspace_id, source, path))
        return [{"path": "specs/auth.md", "name": "auth.md", "kind": "file"}]

    def read_source_doc(self, workspace_id, source, ref):
        self._calls.append(("read", workspace_id, source, ref))
        return {"name": "auth.md", "content": "rotate tokens hourly"}


def _wire(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_resolve_workspace", lambda: "ws-1")
    monkeypatch.setattr(main, "_client", lambda: _FakeClient(calls))
    return calls


def test_search_everything_passes_no_source(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.search("migration", source="", workspace_id=None, limit=20, as_json=True)
    assert calls == [("search", "ws-1", "migration", None, 20)]


def test_search_scoped_passes_the_source(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.search("rotate", source="src-9", workspace_id=None, limit=5, as_json=True)
    assert calls == [("search", "ws-1", "rotate", "src-9", 5)]


def test_sources_browse_and_read(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.sources_browse("src-9", "specs/", workspace_id=None, as_json=True)
    main.sources_read("src-9", "specs/auth.md", workspace_id=None, as_json=True)
    assert ("entries", "ws-1", "src-9", "specs/") in calls
    assert ("read", "ws-1", "src-9", "specs/auth.md") in calls
