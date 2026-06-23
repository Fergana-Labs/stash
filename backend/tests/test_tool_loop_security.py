from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.config import settings
from backend.services import tool_loop


class FakeTool:
    name = "search_source"
    description = "Search a connected source"
    input_schema = {"type": "object"}

    async def handler(self, args):
        raise RuntimeError("token=secret-token and customer transcript")


class FakeStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def get_final_message(self):
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[
                SimpleNamespace(
                    type="tool_use",
                    id="tool-1",
                    name="search_source",
                    input={"query": "token=secret-token and customer transcript"},
                )
            ],
        )


class FakeMessages:
    def stream(self, **kwargs):
        return FakeStream()


class FakeClient:
    messages = FakeMessages()


@pytest.mark.asyncio
async def test_tool_failures_do_not_log_tool_inputs(monkeypatch):
    captured_logs: list[tuple[str, tuple]] = []

    def capture_error(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(tool_loop, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(tool_loop, "_model_for", lambda tier: "test-model")
    monkeypatch.setattr(tool_loop, "_TOOLS_BY_NAME", {"search_source": FakeTool()})
    monkeypatch.setattr(tool_loop.logger, "error", capture_error)

    events = [
        event
        async for event in tool_loop.stream_tool_loop(
            tier="fast",
            system="system",
            prompt="prompt",
            owner_user_id=uuid4(),
            user_id=uuid4(),
            tool_set=("search_source",),
            max_turns=1,
        )
    ]

    assert events == [
        {"type": "tool_result", "id": "tool-1", "name": "search_source", "ok": False},
        {"type": "end"},
    ]
    assert captured_logs == [
        ("tool %s failed exception_type=%s", ("search_source", "RuntimeError"))
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
