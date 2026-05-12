"""Tests for backend/services/llm.py — model tier resolution and the agent
loop's hard caps. Uses a stub Anthropic client so no real API calls are made.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services import llm


def test_model_for_returns_configured_models():
    quality = llm.model_for(llm.ModelTier.QUALITY)
    fast = llm.model_for(llm.ModelTier.FAST)
    assert quality
    assert fast
    assert quality != fast or quality == "claude-sonnet-4-6"  # if user overrode both to same


@dataclass
class _StubResponse:
    content: list
    stop_reason: str
    usage: SimpleNamespace


class _StubClient:
    """Minimal AsyncAnthropic stand-in. Yields canned responses turn by turn."""

    def __init__(self, scripted_turns: list[_StubResponse]):
        self._turns = list(scripted_turns)
        self.call_count = 0

        class _Messages:
            async def create(_self, **kwargs):
                self.call_count += 1
                if not self._turns:
                    raise AssertionError("stub ran out of scripted turns")
                return self._turns.pop(0)

        self.messages = _Messages()


@pytest.mark.asyncio
async def test_agent_loop_terminates_on_end_turn():
    resp = _StubResponse(
        content=[SimpleNamespace(type="text", text="final answer")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )
    stub = _StubClient([resp])

    async def _exec(name, args):
        return ("{}", "noop")

    with patch.object(llm, "get_async_client", return_value=stub):
        result = await llm.agent_loop(
            llm.ModelTier.QUALITY,
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            execute_tool=_exec,
            caps=llm.AgentLoopCaps(max_turns=8, max_tool_calls=30),
        )

    assert result.text == "final answer"
    assert result.terminated_by == "end_turn"
    assert result.turns_used == 1
    assert result.input_tokens == 100
    assert result.output_tokens == 20


@pytest.mark.asyncio
async def test_agent_loop_executes_tool_then_terminates():
    turn1 = _StubResponse(
        content=[
            SimpleNamespace(type="text", text="thinking"),
            SimpleNamespace(type="tool_use", id="t1", name="echo", input={"x": 1}),
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=50, output_tokens=10),
    )
    turn2 = _StubResponse(
        content=[SimpleNamespace(type="text", text="done")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=60, output_tokens=12),
    )
    stub = _StubClient([turn1, turn2])

    seen = []

    async def _exec(name, args):
        seen.append((name, args))
        return ('{"ok": true}', "1 hit")

    with patch.object(llm, "get_async_client", return_value=stub):
        result = await llm.agent_loop(
            llm.ModelTier.QUALITY,
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "echo", "input_schema": {"type": "object"}}],
            execute_tool=_exec,
            caps=llm.AgentLoopCaps(max_turns=8, max_tool_calls=30),
        )

    assert result.text == "done"
    assert result.tool_calls_used == 1
    assert result.turns_used == 2
    assert result.input_tokens == 110
    assert seen == [("echo", {"x": 1})]


@pytest.mark.asyncio
async def test_agent_loop_respects_max_turns():
    # Every turn the model insists on calling another tool. With max_turns=3,
    # the loop must terminate after the third assistant turn even if no
    # natural end_turn arrives.
    looping_turn = lambda i: _StubResponse(
        content=[
            SimpleNamespace(type="text", text=f"t{i}"),
            SimpleNamespace(type="tool_use", id=f"t{i}", name="echo", input={}),
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    stub = _StubClient([looping_turn(i) for i in range(10)])

    async def _exec(name, args):
        return ("{}", "x")

    with patch.object(llm, "get_async_client", return_value=stub):
        result = await llm.agent_loop(
            llm.ModelTier.QUALITY,
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "echo", "input_schema": {"type": "object"}}],
            execute_tool=_exec,
            caps=llm.AgentLoopCaps(max_turns=3, max_tool_calls=30),
        )

    assert result.terminated_by == "max_turns"
    assert result.turns_used == 3


@pytest.mark.asyncio
async def test_agent_loop_respects_max_tool_calls():
    # Each turn fires 2 tool calls; max_tool_calls=3 should cut the loop after
    # the second turn (1 + 2 used, then 2 more attempted but only 1 fits).
    def turn_with_two_tools():
        return _StubResponse(
            content=[
                SimpleNamespace(type="tool_use", id="a", name="echo", input={}),
                SimpleNamespace(type="tool_use", id="b", name="echo", input={}),
            ],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

    stub = _StubClient([turn_with_two_tools() for _ in range(10)])

    async def _exec(name, args):
        return ("{}", "x")

    with patch.object(llm, "get_async_client", return_value=stub):
        result = await llm.agent_loop(
            llm.ModelTier.QUALITY,
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "echo", "input_schema": {"type": "object"}}],
            execute_tool=_exec,
            caps=llm.AgentLoopCaps(max_turns=10, max_tool_calls=3),
        )

    assert result.terminated_by == "max_tool_calls"
    assert result.tool_calls_used == 3
