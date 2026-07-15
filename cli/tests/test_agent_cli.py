"""The `stash agent` sub-app drives cloud agent turns over the agent-chat API.
These lock in the wiring (name→id resolution, the endpoints each command hits)
and the SSE parsing the live stream depends on."""

import httpx
import pytest
import typer

from cli import main
from cli.client import StashClient, StashError

_AGENTS = [
    {"id": "ag-1", "name": "Default", "run_mode": "chat", "model_provider": None},
    {"id": "ag-2", "name": "Reporter", "run_mode": "scheduled", "model_provider": "anthropic"},
]


class _FakeClient:
    def __init__(self, calls: list):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def list_agents(self):
        self._calls.append(("list_agents",))
        return _AGENTS

    def agent_chat_events(self, message, session_id=None, agent_id=None):
        self._calls.append(("chat", message, session_id, agent_id))
        yield {"type": "session", "session_id": "agent-abc"}
        yield {"type": "text", "delta": "hello"}
        yield {"type": "end"}

    def agent_run_events(self, agent_id):
        self._calls.append(("run", agent_id))
        yield {"type": "text", "delta": "ran"}
        yield {"type": "end"}

    def agent_turn_status(self, session_id):
        self._calls.append(("status", session_id))
        return {"session_id": session_id, "running": False}

    def get_agent_chat(self, session_id):
        self._calls.append(("get_chat", session_id))
        return {
            "session_id": session_id,
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "done"},
            ],
        }

    def stop_agent_turn(self, session_id):
        self._calls.append(("stop", session_id))
        return {"stopping": True}


def _wire(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(main, "_client", lambda: _FakeClient(calls))
    return calls


def test_chat_resolves_agent_name_to_id(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.agent_chat("do the thing", session=None, agent="reporter")
    assert ("chat", "do the thing", None, "ag-2") in calls


def test_chat_with_unknown_agent_fails_loud(monkeypatch) -> None:
    _wire(monkeypatch)
    with pytest.raises(typer.Exit):
        main.agent_chat("hi", session=None, agent="nope")


def test_chat_continues_a_session(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.agent_chat("more", session="agent-abc", agent=None)
    assert ("chat", "more", "agent-abc", None) in calls


def test_run_and_stop_hit_their_endpoints(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.agent_run("Reporter")
    main.agent_stop("agent-abc")
    assert ("run", "ag-2") in calls
    assert ("stop", "agent-abc") in calls


def test_watch_polls_until_idle_and_prints_messages(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.agent_watch("agent-abc", poll_seconds=0)
    # Status is fetched before messages so a turn ending between the two
    # calls still gets its final message printed.
    assert calls.index(("status", "agent-abc")) < calls.index(("get_chat", "agent-abc"))


def _sse_client(body: bytes, status_code: int = 200) -> StashClient:
    def handler(request):
        return httpx.Response(status_code, content=body)

    c = StashClient("http://test")
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return c


def test_sse_stream_parses_data_lines_and_skips_keepalives() -> None:
    body = (
        b'data: {"type": "session", "session_id": "agent-1"}\n\n: ping\n\ndata: {"type": "end"}\n\n'
    )
    events = list(_sse_client(body).agent_chat_events("hi"))
    assert events == [{"type": "session", "session_id": "agent-1"}, {"type": "end"}]


def test_sse_stream_surfaces_http_errors() -> None:
    client = _sse_client(b'{"detail": "Connect your Claude key"}', status_code=402)
    with pytest.raises(StashError) as exc:
        list(client.agent_chat_events("hi"))
    assert exc.value.status_code == 402
    assert "Connect" in str(exc.value.detail)
