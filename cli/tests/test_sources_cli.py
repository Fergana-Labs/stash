"""The `stash sources` sub-app + unified `stash search` are thin wrappers over
the client's VFS methods. These lock in the wiring: the right client method is
called with the source-optional arguments, so search-everything and
search-one-source both reach the server correctly."""

from cli import main
from cli.client import StashClient


class _FakeClient:
    def __init__(self, calls: list):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def search_sources(self, query, source=None, limit=20):
        self._calls.append(("search", query, source, limit))
        return [{"source": "files", "ref": "p1", "name": "Runbook", "snippet": "deploy"}]

    def list_sources(self):
        self._calls.append(("list",))
        return [
            {
                "source": "files",
                "type": "native_files",
                "capability": "navigable",
                "display_name": "Files",
            }
        ]

    def list_source_entries(self, source, path=""):
        self._calls.append(("entries", source, path))
        return [{"path": "specs/auth.md", "name": "auth.md", "kind": "file"}]

    def read_source_doc(self, source, ref):
        self._calls.append(("read", source, ref))
        return {"name": "auth.md", "content": "rotate tokens hourly"}


def _wire(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: _FakeClient(calls))
    return calls


def test_search_everything_passes_no_source(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.search("migration", source="", limit=20, as_json=True)
    assert calls == [("search", "migration", None, 20)]


def test_search_scoped_passes_the_source(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.search("rotate", source="src-9", limit=5, as_json=True)
    assert calls == [("search", "rotate", "src-9", 5)]


def test_list_source_entries_sends_path_as_query_param(monkeypatch) -> None:
    """The entries endpoint takes a query param literally named "path". The real
    client method must not collide with the helpers' URL argument (it did once:
    `_list() got multiple values for argument 'path'`)."""
    requests: list = []

    class _Resp:
        def json(self):
            return {"entries": [{"path": "a.md"}]}

    def fake_request(method, url, **kwargs):
        requests.append((method, url, kwargs.get("params")))
        return _Resp()

    client = StashClient("http://test")
    monkeypatch.setattr(client, "_request", fake_request)
    entries = client.list_source_entries("src-9", path="specs/")
    assert entries == [{"path": "a.md"}]
    assert requests == [("GET", "/api/v1/me/sources/src-9/entries", {"path": "specs/"})]
