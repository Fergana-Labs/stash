from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from backend.services import llm


class Decision(BaseModel):
    accepted: bool


async def test_structured_completion_requests_and_returns_validated_schema(monkeypatch):
    decision = Decision(accepted=True)
    parse = AsyncMock(return_value=SimpleNamespace(parsed_output=decision))
    monkeypatch.setattr(llm, "_client", SimpleNamespace(messages=SimpleNamespace(parse=parse)))

    result = await llm.complete_structured(
        prompt="Example",
        system="Classify",
        output_model=Decision,
        tier=llm.ModelTier.QUALITY,
        max_tokens=100,
    )

    assert result is decision
    assert parse.call_args.kwargs["output_format"] is Decision


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_missing_structured_output_is_not_treated_as_abstention(monkeypatch, stop_reason):
    parse = AsyncMock(return_value=SimpleNamespace(parsed_output=None, stop_reason=stop_reason))
    monkeypatch.setattr(llm, "_client", SimpleNamespace(messages=SimpleNamespace(parse=parse)))

    with pytest.raises(ValueError, match=stop_reason):
        await llm.complete_structured(
            prompt="Example",
            system="Classify",
            output_model=Decision,
            tier=llm.ModelTier.QUALITY,
            max_tokens=100,
        )
