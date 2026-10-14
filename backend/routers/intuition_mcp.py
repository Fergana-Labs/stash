"""Intuitions over MCP: everything the wizard does, as tools any agent can call.

Mounted at /mcp/intuitions (streamable HTTP, stateless, JSON responses so it
survives proxies). Authenticate with the same bearer token as the REST API:
`Authorization: Bearer <stash API key>`. Every tool is a thin wrapper over the
services the REST routes and the wizard use, so behavior is identical.

The intended loop for an agent:
    create_intuition -> save_brief -> add_examples / generate_examples
    -> label_example (or accept_suggestions when the user says so)
    -> train -> classify (in the agent's own loop) -> inbox / review_prediction
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from ..auth import authenticate_token
from ..services.intuition import curation, feedback, fusion, service, wizard

INSTRUCTIONS = """Build and use intuitions: small calibrated classifiers that capture a person's \
judgment from a handful of labeled examples (a Jev judge answering rubric criteria, plus a \
learned head, an embedding probe, and held-out measurement). Use them to verify an agent's work \
inside its loop, monitor production, gate regressions, or score prompt optimization and \
post-training.

Building one well: pin down ONE decision; pick labels (choice = exactly one; multi = any subset \
of issues; preference = good/bad) with a boundary for each; record the costlier mistake and the \
cases it must never get wrong (save_brief; the brief is compiled into what the judge reads); add \
8+ real labeled examples covering every label (generate_examples proposes borderline ones for a \
person to confirm); train; read held-out accuracy WITH its sample size; ship when the gate passes. \
Never invent labels on the user's behalf: proposed labels need a person's confirmation."""

mcp = FastMCP(
    "stash-intuitions",
    instructions=INSTRUCTIONS,
    stateless_http=True,
    json_response=True,
    streamable_http_path="/intuitions",
    # Served behind the app's own host and proxy; requests are authenticated per call.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


async def _user(ctx: Context) -> dict:
    request = ctx.request_context.request
    header = (request.headers.get("authorization") if request is not None else None) or ""
    if not header.lower().startswith("bearer "):
        raise ValueError("Send Authorization: Bearer <your Stash API key>")
    user = await authenticate_token(header[7:].strip())
    if not user.get("reward_models_enabled"):
        raise ValueError("Intuitions are not enabled for this account")
    return user


def _id(value: str) -> UUID:
    return UUID(value)


@mcp.tool()
async def list_intuitions(ctx: Context) -> list[dict]:
    """Your intuitions with their live version and held-out accuracy."""
    user = await _user(ctx)
    rows = await service.list_models(user["id"])
    return [
        {
            "id": str(m["id"]),
            "name": m["name"],
            "output_type": m["output_type"],
            "live_version": m["active_number"],
            "held_out_accuracy": ((m.get("active_metrics") or {}).get("eval") or {}).get(
                "accuracy"
            ),
            "examples": m["examples"],
            "inbox": m["inbox"],
        }
        for m in rows
    ]


@mcp.tool()
async def create_intuition(
    ctx: Context,
    name: str,
    output_type: Literal["choice", "multi", "preference"],
    instructions: str,
    labels: list[dict] | None = None,
    brief: dict | None = None,
) -> dict:
    """Create an intuition.

    labels: [{"id": "slug", "description": "..."}] -- choice: 2-12 labels, exactly one applies;
    multi: 1-8 issues, any subset applies ("none" is reserved); preference: omit.
    brief: optional eval brief (see save_brief).
    """
    user = await _user(ctx)
    detail = await service.create_model(
        user["id"],
        name=name[:160],
        output_type=output_type,
        description=instructions,
        labels=labels or [],
        rubric=[],
    )
    model_id = detail["model"]["id"]
    if brief:
        await curation.save_brief(user["id"], model_id, brief)
    return {"id": str(model_id), "status": await wizard.status(user["id"], str(model_id))}


@mcp.tool()
async def get_intuition(ctx: Context, intuition_id: str) -> dict:
    """Everything about one intuition: brief and what it lacks, labels, criteria, example counts, latest training."""
    user = await _user(ctx)
    return await wizard.status(user["id"], intuition_id)


@mcp.tool()
async def save_brief(ctx: Context, intuition_id: str, fields: dict[str, Any]) -> dict:
    """Merge fields into the eval brief (null clears one). Fields: decision, input, labels
    ([{id, means, not}]), costly_mistake, must_never ([str]), edge_cases ([str]), context, success,
    reviewers ([str]). The brief is compiled into the instructions the judge reads."""
    user = await _user(ctx)
    return await curation.save_brief(user["id"], _id(intuition_id), fields)


@mcp.tool()
async def add_examples(ctx: Context, intuition_id: str, examples: list[dict]) -> dict:
    """Add examples: [{"item": str | object, "label"?: str, "note"?: why, "pinned"?: bool}].
    Unlabeled items wait for a person. Multi labels are issue ids joined by '+', or 'none'.
    Pinned examples are regression tests: no version can ship if it gets one wrong."""
    user = await _user(ctx)
    rows = [
        {
            "item": e["item"],
            "item_b": e.get("item_b"),
            "label": e.get("label"),
            "needs_review": not e.get("label"),
            "note": e.get("note", ""),
            "pinned": bool(e.get("pinned") and e.get("label")),
        }
        for e in examples[:200]
    ]
    created = await service.add_examples(user["id"], _id(intuition_id), rows, "agent")
    return {"added": len(created), "ids": [e["id"] for e in created]}


@mcp.tool()
async def generate_examples(
    ctx: Context, intuition_id: str, count: int = 8, guidance: str = "", propose: bool = True
) -> list[dict]:
    """Draft borderline example inputs; with propose, each has a suggested label and reason.
    They stay unconfirmed until a person labels them or calls accept_suggestions."""
    user = await _user(ctx)
    created = await service.generate_examples(
        user["id"], _id(intuition_id), min(count, 20), guidance, propose
    )
    return [
        {"id": e["id"], "item": e["item"], "suggested_label": e["label"], "note": e["note"]}
        for e in created
    ]


@mcp.tool()
async def list_examples(
    ctx: Context, intuition_id: str, only_unconfirmed: bool = False
) -> list[dict]:
    """Examples with their label, split (train / held-out), pin and note."""
    user = await _user(ctx)
    rows = await service.list_examples(user["id"], _id(intuition_id))
    return [
        {
            k: e[k]
            for k in (
                "id",
                "item",
                "item_b",
                "label",
                "needs_review",
                "split",
                "pinned",
                "note",
                "source",
            )
        }
        for e in rows
        if e["needs_review"] or not only_unconfirmed
    ]


@mcp.tool()
async def label_example(
    ctx: Context,
    intuition_id: str,
    example_id: str,
    label: str,
    note: str | None = None,
    pinned: bool | None = None,
) -> dict:
    """Set (or confirm) an example's label, with an optional reason and pin."""
    user = await _user(ctx)
    changes: dict[str, Any] = {"label": label, "needs_review": False}
    if note is not None:
        changes["note"] = note
    if pinned is not None:
        changes["pinned"] = pinned
    return await service.update_example(user["id"], _id(intuition_id), _id(example_id), changes)


@mcp.tool()
async def accept_suggestions(ctx: Context, intuition_id: str) -> dict:
    """Accept every pending suggested label. Only when the person asked for it."""
    user = await _user(ctx)
    return {"accepted": await service.accept_suggestions(user["id"], _id(intuition_id))}


@mcp.tool()
async def propose_criteria(
    ctx: Context,
    intuition_id: str,
    mode: Literal["contrastive", "describe"] = "contrastive",
    count: int = 4,
) -> list[dict]:
    """Draft rubric criteria (not saved). contrastive compares similar items labeled differently."""
    user = await _user(ctx)
    if mode == "contrastive":
        found = await fusion.discover_criteria(user["id"], _id(intuition_id), count)
        return [{**i["question"], "insight": i["insight"]} for i in found["insights"]]
    drafted = await service.draft_rubric(user["id"], _id(intuition_id), count, "")
    return drafted["rubric"]


@mcp.tool()
async def set_criteria(ctx: Context, intuition_id: str, questions: list[dict]) -> dict:
    """Replace the criteria: [{id, type: noul|choice|score, prompt, criteria}] (noul criteria:
    {"true": ..., "false": ...}). Jev answers each one; the head learns how much each matters."""
    user = await _user(ctx)
    model_id = _id(intuition_id)
    draft = await service.ensure_draft(user["id"], model_id)
    signals = [q for q in draft["rubric"] if fusion.is_signal(q["id"])]
    await service.update_draft(
        user["id"], model_id, {"rubric": wizard._clean_questions(questions) + signals}
    )
    return {"saved": len(questions)}


@mcp.tool()
async def train(ctx: Context, intuition_id: str) -> dict:
    """Train on the confirmed labels and report held-out results. Takes up to a minute."""
    user = await _user(ctx)
    report = await fusion.train(user["id"], _id(intuition_id))
    return {
        "held_out": {k: report["holdout"][k] for k in ("n", "accuracy", "accuracy_interval")},
        "zero_shot_accuracy": next(
            (r["accuracy"] for r in report["leaderboard"] if r["name"] == "Jev zero-shot"), None
        ),
        "top_drivers": [d["prompt"] for d in report["drivers"][:3]],
        "gate_passed": report["gate"]["passed"],
        "warnings": report["warnings"],
    }


@mcp.tool()
async def ship(ctx: Context, intuition_id: str, force: bool = False) -> dict:
    """Make the trained draft the live version (refuses if the gate fails unless force)."""
    user = await _user(ctx)
    detail = await service.promote(user["id"], _id(intuition_id), force=force)
    return {"live_version": detail["active"]["number"]}


@mcp.tool()
async def classify(
    ctx: Context,
    intuition_id: str,
    item: Any,
    version: Literal["active", "draft"] = "active",
    ref: str | None = None,
) -> dict:
    """Run the intuition on one input (text or a JSON object). Returns the label, probabilities,
    confidence and a prediction_id for feedback. Logged to the inbox for review."""
    user = await _user(ctx)
    out = await service.predict(
        user["id"], _id(intuition_id), item, which=version, caller="mcp", ref=ref
    )
    return {
        k: out.get(k)
        for k in ("prediction_id", "label", "issues", "probabilities", "confidence", "version")
    }


@mcp.tool()
async def inbox(ctx: Context, intuition_id: str, limit: int = 20) -> list[dict]:
    """Recent decisions waiting for review, least confident first."""
    user = await _user(ctx)
    rows = await curation.queue(user["id"], _id(intuition_id), "all", limit=limit)
    return [
        {
            "prediction_id": str(r["id"]),
            "item": r["input"].get("item"),
            "label": curation.predicted_label(r["output"]),
            "confidence": r["confidence"],
        }
        for r in rows
    ]


@mcp.tool()
async def review_prediction(
    ctx: Context,
    intuition_id: str,
    prediction_id: str,
    label: str,
    note: str = "",
    pin: bool = False,
) -> dict:
    """Confirm or correct a decision; it becomes a golden example (with the reason, optionally pinned)."""
    user = await _user(ctx)
    result = await curation.resolve(
        user["id"], _id(intuition_id), _id(prediction_id), label, note, pin
    )
    return {"example_id": (result["example"] or {}).get("id")}


@mcp.tool()
async def give_feedback(
    ctx: Context,
    intuition_id: str,
    label: str,
    prediction_id: str | None = None,
    ref: str | None = None,
    note: str = "",
) -> dict:
    """Record what actually happened for a decision (by prediction_id or your own ref), e.g. from a
    downstream check. Stored as feedback; it does not become a training label on its own."""
    user = await _user(ctx)
    out = await feedback.record(
        user["id"],
        _id(intuition_id),
        prediction_id=_id(prediction_id) if prediction_id else None,
        ref=ref,
        label=label,
        source="downstream",
        note=note,
    )
    return {"recorded": True, "prediction_id": out["prediction_id"]}


app = mcp.streamable_http_app()
