"""Which kinds of model exist.

A kind is a module under `kinds/` that provides:

    TITLE: str                      shown to people
    BASE_MODEL: str                 recorded on every model row
    PRICE_SETTING: str              the Settings attribute holding its Stripe price id
    check_corpus(documents) -> CorpusReport
    async start_training(name, report) -> str          the GPU job reference
    async training_result(job_ref) -> dict | None      None while still running
    OPS: dict[str, type[BaseModel]]                    operation name -> input schema
    async run(model, op, payload) -> dict              start a generation, wait a little
    async job_result(model, job_id) -> dict            poll a generation that went pending
    register_tools(mcp, current_user) -> None          the kind's own MCP tools

Looking up a kind that does not exist is a programming error or a bad
request, never something to paper over: callers get a KeyError.
"""

from __future__ import annotations

from types import ModuleType

from .kinds import stylewriter

KINDS: dict[str, ModuleType] = {"stylewriter": stylewriter}


def get(kind: str) -> ModuleType:
    if kind not in KINDS:
        raise KeyError(f"unknown model kind {kind!r}; known kinds: {', '.join(KINDS)}")
    return KINDS[kind]
