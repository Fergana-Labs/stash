import json
from unittest.mock import AsyncMock

import pytest

from backend.services.rm import trace_titles
from backend.services.rm.adapters import CanonicalStep, CanonicalTrace


async def test_title_summarizes_agent_actions_and_outcome(monkeypatch):
    trace = CanonicalTrace(
        external_id=None,
        title=None,
        metadata={},
        steps=[
            CanonicalStep(role="user", content="Help with my order"),
            CanonicalStep(
                role="assistant", content="", tool_name="refund", tool_input={"id": "B2"}
            ),
            CanonicalStep(role="tool", content="Refund issued"),
            CanonicalStep(role="assistant", content="Your refund is on its way"),
        ],
    )
    complete = AsyncMock(return_value="Order refund issued")
    monkeypatch.setattr(trace_titles.llm, "complete_text", complete)
    assert await trace_titles.generate_title(trace) == "Order refund issued"
    source = json.loads(complete.call_args.kwargs["prompt"])
    assert source[1]["tool_input"] == {"id": "B2"}
    assert source[-1]["content"] == "Your refund is on its way"


@pytest.mark.parametrize("title", ["", "a" * 81, "Title\nMore text"])
async def test_invalid_generated_title_is_an_error(monkeypatch, title):
    monkeypatch.setattr(trace_titles.llm, "complete_text", AsyncMock(return_value=title))
    trace = CanonicalTrace(None, None, {}, [CanonicalStep("user", "hi")])
    with pytest.raises(ValueError, match="invalid title"):
        await trace_titles.generate_title(trace)
