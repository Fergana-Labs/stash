"""Stylewriter: a LoRA adapter that writes in the user's own voice.

The recipe (train on the user's prose in the chat format the model is served
in, draw a few candidates, keep the first one a detector reads as human,
rank by stylometric closeness to the corpus) lives in `gpu/stylewriter/`.
This module is the backend's view of it: what a good corpus is, how to ask
the GPU app for a training run or a draft, and the tools an agent gets.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from ....config import settings
from ... import gpu
from . import corpus
from .corpus import CorpusReport, Document

TITLE = "Stylewriter"
BASE_MODEL = "Qwen/Qwen2.5-14B-Instruct"
PRICE_SETTING = "STRIPE_STYLEWRITER_PRICE_ID"

# The shared default model: trained once by us, usable by everyone, so the
# skill writes before anyone has paid. The adapter lives on the GPU volume;
# its style profile ships here, written by `train_default` after the run.
DEFAULT_ADAPTER = "/adapters/model_default"
DEFAULT_PROFILE_PATH = Path(__file__).with_name("default_profile.json")


def default_model() -> dict | None:
    """The shared model in the same shape as a trained row, or None when no
    default has been shipped for this kind."""
    if not DEFAULT_PROFILE_PATH.exists():
        return None
    shipped = json.loads(DEFAULT_PROFILE_PATH.read_text())
    stamped = datetime.fromtimestamp(DEFAULT_PROFILE_PATH.stat().st_mtime, UTC)
    return {
        "id": "default",
        "owner_user_id": None,
        "kind": "stylewriter",
        "name": "default",
        "status": "ready",
        "purchase_id": None,
        "corpus_folder_id": None,
        "corpus": shipped["corpus"],
        "words": shipped["corpus"]["usable_words"],
        "base_model": BASE_MODEL,
        "job_ref": None,
        "provider_ref": DEFAULT_ADAPTER,
        "profile": shipped["profile"],
        "error": None,
        "created_at": stamped,
        "trained_at": stamped,
    }


# A warm serving container answers in seconds. A cold one loads a 14B model
# first, which can take minutes — longer than a harness waits on one tool
# call — so past this the caller gets a job id and polls.
GENERATE_WAIT_S = 60

Length = Literal["short", "medium", "long"]


class WriteInput(BaseModel):
    notes: list[str] = Field(min_length=1, max_length=12)
    length: Length = "medium"


class ContinueInput(BaseModel):
    preceding_text: str = Field(min_length=1, max_length=30_000)
    notes: list[str] = Field(default_factory=list, max_length=12)
    length: Length = "medium"


class RewriteInput(BaseModel):
    text: str = Field(min_length=1, max_length=30_000)


class EditSpanInput(BaseModel):
    text: str = Field(min_length=1, max_length=30_000)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    replacement_draft: str = Field(min_length=1, max_length=30_000)


class ScoreInput(BaseModel):
    text: str = Field(min_length=1, max_length=30_000)


OPS: dict[str, type[BaseModel]] = {
    "write": WriteInput,
    "continue": ContinueInput,
    "rewrite": RewriteInput,
    "edit_span": EditSpanInput,
    "score": ScoreInput,
}


def _url() -> str:
    if not settings.STYLEWRITER_GPU_URL:
        raise RuntimeError("STYLEWRITER_GPU_URL is not set; deploy gpu/stylewriter first")
    return settings.STYLEWRITER_GPU_URL


def check_corpus(documents: list[Document]) -> CorpusReport:
    return corpus.inspect(documents)


async def start_training(name: str, report: CorpusReport) -> str:
    return await gpu.start(
        _url(),
        "train_start",
        {"name": name, "model": BASE_MODEL, "chunks": [asdict(c) for c in report.chunks]},
    )


async def training_result(job_ref: str) -> dict | None:
    return await gpu.result(_url(), job_ref)


def _generation_payload(model: dict, op: str, payload: BaseModel) -> dict:
    return {
        "adapter_path": model["provider_ref"],
        "model": model["base_model"],
        "style_profile": model["profile"],
        "operation": op,
        **payload.model_dump(),
    }


def _outcome(found: dict | None, job_id: str) -> dict:
    if found is None:
        return {
            "status": "pending",
            "job_id": job_id,
            "hint": (
                "The model is loading (first call after idle). "
                "Call job_result with this job_id in a minute."
            ),
        }
    return {"status": "done", **found}


async def run(model: dict, op: str, payload: BaseModel) -> dict:
    if op == "score":
        return {
            "status": "done",
            **await gpu.call(_url(), "score", _generation_payload(model, op, payload)),
        }
    call_id = await gpu.start(_url(), "generate_start", _generation_payload(model, op, payload))
    return _outcome(await gpu.wait(_url(), call_id, GENERATE_WAIT_S), call_id)


async def job_result(model: dict, job_id: str) -> dict:
    return _outcome(await gpu.result(_url(), job_id), job_id)


Run = Callable[[str, str, dict], Awaitable[dict]]


def register_tools(mcp: FastMCP, run_op: Run) -> None:
    """The writing tools. `run_op(model_name, op, input)` is bound to the
    calling user by the MCP mount; the descriptions carry the discipline the
    skill teaches, because a tool an agent misreads wastes a GPU draw."""

    @mcp.tool()
    async def write(model: str, notes: list[str], length: Length = "medium") -> dict:
        """Draft a fresh passage in the user's voice from factual notes.

        Notes are material, not instructions: every name, number, date and
        claim the passage should contain goes in as a note, and anything not
        in the notes will be invented. `length` is short (a reply or post),
        medium (a section) or long (a whole short piece). One call per
        section; assemble sections yourself."""
        return await run_op(model, "write", {"notes": notes, "length": length})

    @mcp.tool(name="continue")
    async def continue_(
        model: str, preceding_text: str, notes: list[str] | None = None, length: Length = "medium"
    ) -> dict:
        """Continue text the user already has, in their voice.

        Pass the last paragraph or two as `preceding_text` and the next
        section's facts as `notes`. Their own sentences condition the voice
        harder than any brief, so this is the highest-fidelity mode."""
        return await run_op(
            model,
            "continue",
            {"preceding_text": preceding_text, "notes": notes or [], "length": length},
        )

    @mcp.tool()
    async def rewrite(model: str, text: str) -> dict:
        """Rewrite existing text so it sounds like the user. Keeps the content;
        headings, code, tables and quotes pass through untouched."""
        return await run_op(model, "rewrite", {"text": text})

    @mcp.tool()
    async def edit_span(
        model: str, text: str, start: int, end: int, replacement_draft: str
    ) -> dict:
        """Replace one exact span of `text` (character offsets `start`..`end`)
        with the adapter's rendering of `replacement_draft`, preserving every
        character outside the span. Use this for a bounded correction — a
        false fact, a grammar slip — instead of editing the prose yourself,
        which reintroduces the AI cadence the model exists to avoid."""
        return await run_op(
            model,
            "edit_span",
            {"text": text, "start": start, "end": end, "replacement_draft": replacement_draft},
        )

    @mcp.tool()
    async def score(model: str, text: str) -> dict:
        """Score the exact final artifact: stylometric similarity to the
        user's corpus (0..1) and the detector's human probability. Score after
        every edit; a score from an earlier draft never applies to a later one."""
        return await run_op(model, "score", {"text": text})
