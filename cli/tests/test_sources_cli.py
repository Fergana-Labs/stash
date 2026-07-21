"""The `stash sources` sub-app + unified `stash search` are thin wrappers over
the client's VFS methods. These lock in the wiring: the right client method is
called with the source-optional arguments, so search-everything and
search-one-source both reach the server correctly."""

from cli import main
from cli.client import StashClient, split_source_tokens


class _FakeClient:
    def __init__(self, calls: list):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def search_sources(
        self, query, source=None, include_sources=None, exclude_sources=None, limit=20, offset=0
    ):
        self._calls.append(
            ("search", query, source, include_sources, exclude_sources, limit, offset)
        )
        return {
            "results": [{"source": "files", "ref": "p1", "name": "Runbook", "snippet": "deploy"}],
            "has_more": False,
        }

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
    main.search(
        "migration", source="", include_sources="", exclude_sources="", limit=20, as_json=True
    )
    assert calls == [("search", "migration", None, None, None, 20, 0)]


def test_search_scoped_passes_the_source(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.search(
        "rotate", source="src-9", include_sources="", exclude_sources="", limit=5, as_json=True
    )
    assert calls == [("search", "rotate", "src-9", None, None, 5, 0)]


def test_search_splits_comma_separated_source_filters(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.search(
        "migration",
        source="",
        include_sources="files, gmail,,jira",
        exclude_sources="slack",
        limit=20,
        as_json=True,
    )
    assert calls == [("search", "migration", None, ["files", "gmail", "jira"], ["slack"], 20, 0)]


def test_split_source_tokens() -> None:
    assert split_source_tokens("") is None
    assert split_source_tokens(" , ") is None
    assert split_source_tokens("files") == ["files"]
    assert split_source_tokens("files, gmail") == ["files", "gmail"]


def test_search_sends_source_filters_as_repeated_query_params(monkeypatch) -> None:
    """The endpoint declares list[str] Query params, which parse repeated
    `?include_sources=a&include_sources=b` params — so the client must hand
    httpx a list, not a joined string."""
    requests: list = []

    class _Resp:
        def json(self):
            return {"results": [], "has_more": False}

    def fake_request(method, url, **kwargs):
        requests.append((method, url, kwargs.get("params")))
        return _Resp()

    client = StashClient("http://test")
    monkeypatch.setattr(client, "_request", fake_request)
    client.search_sources("q", include_sources=["files", "gmail"], exclude_sources=["slack"])
    assert requests == [
        (
            "GET",
            "/api/v1/me/sources/search",
            {
                "q": "q",
                "limit": 20,
                "offset": 0,
                "include_sources": ["files", "gmail"],
                "exclude_sources": ["slack"],
            },
        )
    ]


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


def test_search_renders_error_and_truncation_markers(monkeypatch, capsys) -> None:
    """Non-JSON `stash search` must render marker entries as disclosures — a
    dead source as a warning, a capped result as a "showing first N" note — not
    as blank hit rows."""

    class _MarkerClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def search_sources(
            self, query, source=None, include_sources=None, exclude_sources=None, limit=20, offset=0
        ):
            return {
                "results": [
                    {
                        "source_name": "Gmail (a@b.com)",
                        "ref": "m1",
                        "name": "Hello",
                        "snippet": "hi",
                    },
                    {
                        "source_name": "Gmail (a@b.com)",
                        "truncated": True,
                        "returned": 25,
                        "estimated_total": 213,
                    },
                    {
                        "source_name": "Jira (PROJ)",
                        "error": "reconnect it in Settings",
                        "needs_reconnect": True,
                    },
                ],
                "has_more": True,
            }

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: _MarkerClient())
    main.search("q", source="", include_sources="", exclude_sources="", limit=30, as_json=False)

    out = capsys.readouterr().out
    assert "Hello" in out
    assert "213" in out
    assert "reconnect it in Settings" in out
    assert "More matches exist" in out


def test_search_prints_the_server_snippet_whole(monkeypatch, capsys) -> None:
    """The server already windows each snippet around the query match; a
    client-side cut on top of that would chop off the back half of the window,
    hiding the match it was centered on."""
    snippet = "…" + ("context before the match. " * 12) + "the match itself ZFINALZ…"
    assert len(snippet) > 300  # long enough that a client-side 300-char cut would drop the tail

    class _SnippetClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def search_sources(
            self, query, source=None, include_sources=None, exclude_sources=None, limit=20, offset=0
        ):
            return {
                "results": [{"source": "files", "ref": "p1", "name": "Notes", "snippet": snippet}],
                "has_more": False,
            }

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: _SnippetClient())
    main.search("match", source="", include_sources="", exclude_sources="", limit=20, as_json=False)

    assert "ZFINALZ" in capsys.readouterr().out
