"""Model wizard: a chat agent that walks a user through building a classifier.

The wizard is Claude in a tool loop. Its tools are of two kinds:

- Actions run on the server against the same services the eval UI uses
  (create the model, draft or discover criteria, add or generate examples,
  train, harden, try, ship). Long actions stream progress.
- Cards open an interactive widget inline in the chat (a labeler, an uploader,
  the criteria editor, the training report, a playground, a review queue,
  quick-reply choices). Cards talk to the REST API directly, so they stay live
  and work without the agent; when the user finishes with one, the card posts a
  short event message back into the chat ("Labeled 12 examples ...") and the
  wizard continues from there.

A session's `messages` are the Claude transcript; its `transcript` is what the
chat renders: user turns, and assistant turns as ordered parts (text, cards,
tool activity).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

from ...config import settings
from ...database import get_pool
from .. import llm
from . import fusion, providers, service
from . import probe as probes

log = logging.getLogger(__name__)

MAX_TURNS = 10
MAX_RESULT_CHARS = 12000
MAX_HISTORY_MESSAGES = 80

CARD_KINDS = (
    "choices",
    "uploader",
    "labeler",
    "criteria",
    "report",
    "playground",
    "review",
    "robustness",
    "examples",
)

SYSTEM = """You are the Model Wizard inside Stash. You help a non-expert build a custom \
classifier ("model") for their own judgment calls -- routing tickets, grading outputs, flagging \
risky content, picking the better of two drafts -- with as few examples as possible. It should \
feel effortless, like magic, but never dishonest.

How the models work (explain only when useful, in plain words):
- A judge model (Jev) answers the user's criteria about each item with probabilities, and also \
answers the task itself zero-shot. A small calibrated head learns how much each answer matters \
from the user's labels, starting from "trust the zero-shot verdict", so even 6-10 labels help.
- An embedding probe learns what the user's labeled examples look like, beyond what the \
criteria say.
- Criteria can be discovered contrastively: similar items the user labeled differently are \
compared to find the property that separates them.
- Hardening writes manipulation attempts (fake approvals, instructions to the grader), repairs \
the model with the ones that work, and re-measures on fresh attacks.
- Everything is measured on held-out examples the model never trained on. No LLM weights are \
fine-tuned.
- Inputs can be text, JSON objects, images, PDFs, slides or documents (multimodal). Images are \
described by a vision model for the judge, and shown as images when discovering criteria.

The flow (adapt to the user; skip what they already gave you):
1. Goal: what decision, what an input looks like, which labels. Ask at most two short questions \
at a time; offer quick picks with show_choices. Choice models pick one of 2-12 labels; \
preference models score outputs good/bad or pick the better of two.
2. Create the model as soon as the goal and labels are clear (create_model). Write a rich context \
description: who uses it, what matters, edge cases, what the user said.
3. Examples: ask for real ones (open_uploader: files, images, pasted text/CSV/JSONL) or paste \
them into chat (add_examples). If they have few, generate_examples drafts realistic, borderline \
cases. Then open_labeler so they label quickly. Aim for >= 8 labeled with every label present.
4. Criteria: co-create. Draft with propose_criteria (mode "contrastive" once there are labels of \
two kinds -- prefer it; "describe" before). Discuss them, then open_criteria so the user can \
accept, edit, or remove. You may also write criteria yourself from what the user tells you \
(set_criteria). Ask about observable properties, never the verdict itself.
5. Train (train). The report card opens automatically; summarize it in 2-3 sentences: held-out \
accuracy vs. zero-shot Jev, how sure we can be given the held-out size, the top drivers.
6. Improve: label uncertain cases (open_review), add contrastive criteria, harden, then ship \
(promote) once the gate passes. Then point them to the playground and the API.

When the user asks to do something that a card does (label, upload, edit criteria, see results, \
try it, review predictions, see examples, robustness), open that card. Cards report back with a \
message starting with "[card]". Keep replies short and warm, no jargon unless asked, never \
fabricate numbers -- quote only what tools returned. If a tool fails, say what happened and \
what to do next."""


def _tool(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": properties or {}, "required": required or []},
    }


LABEL_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "lowercase slug, e.g. 'refund_request'"},
            "description": {"type": "string"},
        },
        "required": ["id", "description"],
    },
}
QUESTION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "type": {"type": "string", "enum": ["noul", "choice", "score"]},
            "prompt": {"type": "string"},
            "criteria": {
                "description": "noul: {\"true\": ..., \"false\": ...}; choice: {option: description}; score: list of 3-5 ordered level descriptions, lowest first",
            },
        },
        "required": ["id", "type", "prompt", "criteria"],
    },
}
ITEM_SCHEMA = {"description": "The input: a string, or a JSON object with the same keys as the other items"}

TOOLS = [
    _tool(
        "create_model",
        "Create the model once the goal and labels are clear. Links it to this chat.",
        {
            "name": {"type": "string"},
            "output_type": {"type": "string", "enum": ["choice", "preference"]},
            "description": {"type": "string", "description": "Context for the judge: the goal, who decides, what matters, edge cases."},
            "labels": {**LABEL_SCHEMA, "description": "Choice models only: 2-12 labels. Omit for preference."},
        },
        ["name", "output_type", "description"],
    ),
    _tool(
        "update_model",
        "Change the model's name, context description, or labels.",
        {"name": {"type": "string"}, "description": {"type": "string"}, "labels": LABEL_SCHEMA},
    ),
    _tool("get_status", "Current model state: labels, criteria, example counts, latest training results."),
    _tool(
        "propose_criteria",
        "Draft rubric criteria (not saved) and open the criteria editor with them for the user to accept. "
        "mode 'contrastive' compares similar items labeled differently (needs labels of two kinds); "
        "'describe' drafts from the context and examples.",
        {
            "mode": {"type": "string", "enum": ["contrastive", "describe"]},
            "count": {"type": "integer", "minimum": 1, "maximum": 6},
            "guidance": {"type": "string"},
        },
        ["mode"],
    ),
    _tool(
        "set_criteria",
        "Replace the user's criteria with these questions (max 10). Use after agreeing on them in chat.",
        {"questions": QUESTION_SCHEMA},
        ["questions"],
    ),
    _tool(
        "add_examples",
        "Add examples the user pasted into chat. Unlabeled ones go to the labeler.",
        {
            "examples": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item": ITEM_SCHEMA,
                        "item_b": {"description": "Preference pairs only: the second output"},
                        "label": {"type": "string", "description": "A label id; preference: good|bad, pairs: a|b"},
                    },
                    "required": ["item"],
                },
            }
        },
        ["examples"],
    ),
    _tool(
        "generate_examples",
        "Draft realistic, varied, borderline example inputs for the user to label (then open the labeler).",
        {"count": {"type": "integer", "minimum": 1, "maximum": 20}, "guidance": {"type": "string"}},
    ),
    _tool("train", "Train on the current labels and criteria; opens the training report card. Takes up to a minute."),
    _tool(
        "harden",
        "Red-team the trained model with manipulation attempts, repair it, and re-measure. Opens the robustness card. Takes a few minutes.",
        {"target_label": {"type": "string", "description": "Choice models: the label an attacker wants to get"}},
    ),
    _tool(
        "try_item",
        "Run the trained (draft) model on one input and show the decision with its reasons.",
        {"item": ITEM_SCHEMA},
        ["item"],
    ),
    _tool("promote", "Ship the trained draft as the live version (only when the gate passes, unless the user insists).",
          {"force": {"type": "boolean"}}),
    _tool(
        "show_choices",
        "Show quick-reply buttons. The user's pick comes back as their next message.",
        {
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 6},
            "multi": {"type": "boolean"},
        },
        ["question", "options"],
    ),
    _tool(
        "open_uploader",
        "Open a drop zone for files (images, PDFs, docs, slides, text, CSV/JSONL) and pasted examples.",
        {"prompt": {"type": "string", "description": "One line telling the user what to add"}},
    ),
    _tool(
        "open_labeler",
        "Open the fast labeling card.",
        {"which": {"type": "string", "enum": ["needs_review", "all", "mistakes"]}},
    ),
    _tool("open_criteria", "Open the criteria editor on the current criteria."),
    _tool("open_report", "Open the latest training report."),
    _tool("open_playground", "Open a playground to try inputs (text, JSON, or files) against the model."),
    _tool("open_review", "Open the review queue of recent predictions the model was least sure about."),
    _tool("open_examples", "Open the table of all examples with their labels and splits."),
]


# ── Sessions ─────────────────────────────────────────────────────────────


def _session(row) -> dict:
    s = dict(row)
    s["id"] = str(s["id"])
    s["model_id"] = str(s["model_id"]) if s["model_id"] else None
    return s


async def create_session(owner_id: UUID, model_id: UUID | None = None) -> dict:
    if model_id is not None:
        await service._model(owner_id, model_id)
    row = await get_pool().fetchrow(
        "INSERT INTO intuition_wizard_sessions (owner_user_id, model_id) VALUES ($1, $2) RETURNING *",
        owner_id,
        model_id,
    )
    return _session(row)


async def list_sessions(owner_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT s.id, s.model_id, s.title, s.created_at, s.updated_at, m.name AS model_name
             FROM intuition_wizard_sessions s
             LEFT JOIN intuition_models m ON m.id = s.model_id
            WHERE s.owner_user_id = $1 ORDER BY s.updated_at DESC LIMIT 50""",
        owner_id,
    )
    return [_session(r) for r in rows]


async def get_session(owner_id: UUID, session_id: UUID) -> dict:
    row = await get_pool().fetchrow(
        "SELECT * FROM intuition_wizard_sessions WHERE id = $1 AND owner_user_id = $2",
        session_id,
        owner_id,
    )
    if row is None:
        raise service.NotFound("Wizard session not found")
    return _session(row)


async def delete_session(owner_id: UUID, session_id: UUID) -> None:
    await get_session(owner_id, session_id)
    await get_pool().execute("DELETE FROM intuition_wizard_sessions WHERE id = $1", session_id)


async def _save(session: dict) -> None:
    await get_pool().execute(
        """UPDATE intuition_wizard_sessions
              SET messages = $2, transcript = $3, model_id = $4, title = $5, updated_at = now()
            WHERE id = $1""",
        UUID(session["id"]),
        session["messages"][-MAX_HISTORY_MESSAGES:],
        session["transcript"],
        UUID(session["model_id"]) if session["model_id"] else None,
        session["title"],
    )


# ── State summary given to the wizard every turn ─────────────────────────


async def status(owner_id: UUID, model_id: str | None) -> dict:
    if not model_id:
        return {"model": None, "judge": providers.status(), "embeddings": probes.embeddings.is_configured()}
    detail = await service.get_detail(owner_id, UUID(model_id))
    version = detail["draft"] or detail["active"]
    examples = await service.list_examples(owner_id, UUID(model_id))
    labeled = [e for e in examples if e["label"] and not e["needs_review"]]
    by_label: dict[str, int] = {}
    for e in labeled:
        by_label[e["label"]] = by_label.get(e["label"], 0) + 1
    report = ((version or {}).get("metrics") or {}).get("report")
    return {
        "model": {
            "id": model_id,
            "name": detail["model"]["name"],
            "output_type": detail["model"]["output_type"],
            "description": version["description"],
            "labels": version["labels"],
            "criteria": [{"id": q["id"], "type": q["type"], "prompt": q["prompt"]} for q in fusion.user_questions(version["rubric"])],
            "live_version": detail["active"]["number"] if detail["active"] else None,
            "draft_trained": bool(detail["draft"] and not detail["draft"]["head_stale"]),
        },
        "examples": {
            "total": len(examples),
            "labeled": len(labeled),
            "needs_labels": sum(e["needs_review"] for e in examples),
            "by_label": by_label,
            "held_out": sum(e["split"] == "eval" for e in labeled),
            "images": sum(isinstance(e["item"], dict) and e["item"].get("kind") == "image" for e in examples),
        },
        "latest_training": None
        if not report
        else {
            "held_out_accuracy": report["holdout"]["accuracy"],
            "held_out_n": report["holdout"]["n"],
            "leaderboard": [{k: row.get(k) for k in ("name", "accuracy", "log_loss")} for row in report["leaderboard"]],
            "gate_passed": report["gate"]["passed"],
            "top_drivers": [d["prompt"] for d in report["drivers"][:3]],
        },
        "judge": providers.status(),
    }


# ── Tool execution ───────────────────────────────────────────────────────


def _card(kind: str, **props) -> dict:
    assert kind in CARD_KINDS
    return {"id": uuid.uuid4().hex[:12], "kind": kind, "props": props}


def _need_model(session: dict) -> UUID:
    if not session["model_id"]:
        raise service.Conflict("Create the model first (create_model)")
    return UUID(session["model_id"])


def _clean_questions(questions: list[dict]) -> list[dict]:
    out = []
    for q in questions[:10]:
        criteria = q.get("criteria")
        if q.get("type") == "score" and isinstance(criteria, dict):
            criteria = [criteria[k] for k in sorted(criteria)]
        out.append({"id": q["id"], "type": q["type"], "prompt": q["prompt"], "criteria": criteria})
    return out


async def run_tool(owner_id: UUID, session: dict, name: str, args: dict, progress) -> tuple[dict, dict | None]:
    """Execute one tool. Returns (result for Claude, card to render or None)."""
    if name == "create_model":
        if session["model_id"]:
            raise service.Conflict("This chat already has a model; use update_model")
        labels = args.get("labels") or []
        detail = await service.create_model(
            owner_id,
            name=args["name"][:160],
            output_type=args["output_type"],
            description=args.get("description", ""),
            labels=labels if args["output_type"] == "choice" else [],
            rubric=[],
        )
        session["model_id"] = str(detail["model"]["id"])
        session["title"] = args["name"][:160]
        return {"created": True, "model_id": session["model_id"]}, None
    if name == "update_model":
        model_id = _need_model(session)
        if args.get("name"):
            await service.rename_model(owner_id, model_id, args["name"][:160])
            session["title"] = args["name"][:160]
        changes = {k: args[k] for k in ("description", "labels") if args.get(k) is not None}
        if changes:
            await service.update_draft(owner_id, model_id, changes)
        return {"updated": sorted(changes) + (["name"] if args.get("name") else [])}, None
    if name == "get_status":
        return await status(owner_id, session["model_id"]), None
    if name == "propose_criteria":
        model_id = _need_model(session)
        count = int(args.get("count") or 4)
        if args.get("mode") == "contrastive":
            found = await fusion.discover_criteria(owner_id, model_id, count, args.get("guidance", ""))
            proposals = [{**i["question"], "insight": i["insight"]} for i in found["insights"]]
            summary = {"proposed": [{"prompt": p["prompt"], "insight": p["insight"]} for p in proposals], "contrast_pairs": len(found["pairs"])}
        else:
            drafted = await service.draft_rubric(owner_id, model_id, count, args.get("guidance", ""))
            proposals = drafted["rubric"]
            summary = {"proposed": [p["prompt"] for p in proposals], "rationale": drafted["rationale"]}
        return {**summary, "shown_to_user": "criteria editor"}, _card("criteria", proposals=proposals)
    if name == "set_criteria":
        model_id = _need_model(session)
        draft = await service.ensure_draft(owner_id, model_id)
        signals = [q for q in draft["rubric"] if q["id"] in fusion.SIGNAL_IDS]
        await service.update_draft(owner_id, model_id, {"rubric": _clean_questions(args["questions"]) + signals})
        return {"saved": len(args["questions"])}, _card("criteria")
    if name == "add_examples":
        model_id = _need_model(session)
        rows = [
            {
                "item": e["item"],
                "item_b": e.get("item_b"),
                "label": e.get("label"),
                "needs_review": not e.get("label"),
                "note": "" if e.get("label") else "Added in the wizard; needs a label",
            }
            for e in args["examples"][:200]
        ]
        created = await service.add_examples(owner_id, model_id, rows, "human")
        unlabeled = sum(r["needs_review"] for r in rows)
        return {"added": len(created), "unlabeled": unlabeled}, None
    if name == "generate_examples":
        model_id = _need_model(session)
        created = await service.generate_examples(owner_id, model_id, int(args.get("count") or 10), args.get("guidance", ""))
        return {"generated": len(created), "note": "They need labels; open the labeler."}, None
    if name == "train":
        model_id = _need_model(session)
        report = await fusion.train(owner_id, model_id, progress)
        brief = {
            "held_out": report["holdout"] | {"rows": None, "reliability": None, "confusion": None},
            "leaderboard": report["leaderboard"],
            "drivers": report["drivers"][:5],
            "learning_curve": report["learning_curve"],
            "gate_passed": report["gate"]["passed"],
            "warnings": report["warnings"],
        }
        return brief, _card("report")
    if name == "harden":
        model_id = _need_model(session)
        result = await fusion.harden(owner_id, model_id, args.get("target_label"), progress)
        return result, _card("robustness", result=result)
    if name == "try_item":
        model_id = _need_model(session)
        out = await service.predict(owner_id, model_id, args["item"], which="draft", caller="wizard", log=True)
        brief = {k: out[k] for k in ("label", "probabilities", "confidence")}
        return brief, _card("playground", item=args["item"], prediction=out)
    if name == "promote":
        model_id = _need_model(session)
        detail = await service.promote(owner_id, model_id, force=bool(args.get("force")))
        return {"live_version": detail["active"]["number"]}, None
    if name == "show_choices":
        return {"shown": True}, _card("choices", question=args["question"], options=args["options"][:6], multi=bool(args.get("multi")))
    card_tools = {
        "open_uploader": ("uploader", {"prompt": args.get("prompt", "")}),
        "open_labeler": ("labeler", {"which": args.get("which", "needs_review")}),
        "open_criteria": ("criteria", {}),
        "open_report": ("report", {}),
        "open_playground": ("playground", {}),
        "open_review": ("review", {}),
        "open_examples": ("examples", {}),
    }
    if name in card_tools:
        _need_model(session)
        kind, props = card_tools[name]
        return {"shown": True, "note": "The user will report back when done."}, _card(kind, **props)
    raise ValueError(f"Unknown tool {name}")


# ── The turn loop ────────────────────────────────────────────────────────


def _blocks(content) -> list[dict]:
    out = []
    for block in content:
        if block.type == "text" and block.text:
            out.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            out.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
    return out


ACTIVITY = {
    "create_model": "Creating the model",
    "update_model": "Updating the model",
    "get_status": "Checking the model",
    "propose_criteria": "Drafting criteria",
    "set_criteria": "Saving criteria",
    "add_examples": "Adding examples",
    "generate_examples": "Drafting examples",
    "train": "Training",
    "harden": "Red-teaming",
    "try_item": "Running the model",
    "promote": "Shipping",
}


async def stream_turn(owner_id: UUID, session_id: UUID, text: str, kind: str = "message") -> AsyncIterator[dict]:
    session = await get_session(owner_id, session_id)
    session["transcript"].append({"role": "user", "kind": kind, "text": text})
    said = text if kind == "message" else f"[card] {text}"
    last = session["messages"][-1] if session["messages"] else None
    if last and last["role"] == "user" and isinstance(last["content"], list):
        # A turn that ran out of steps ends on tool results; the next message joins that user turn.
        last["content"].append({"type": "text", "text": said})
    else:
        session["messages"].append({"role": "user", "content": said})
    parts: list[dict] = []
    session["transcript"].append({"role": "assistant", "parts": parts})
    client = llm._get_client()
    try:
        for _ in range(MAX_TURNS):
            state = await status(owner_id, session["model_id"])
            system = SYSTEM + "\n\nCURRENT STATE (authoritative):\n" + json.dumps(state, default=str)
            async with client.messages.stream(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=4096,
                system=system,
                tools=TOOLS,
                messages=session["messages"],
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        if not parts or parts[-1]["type"] != "text":
                            parts.append({"type": "text", "text": ""})
                        parts[-1]["text"] += event.delta.text
                        yield {"type": "text", "delta": event.delta.text}
                final = await stream.get_final_message()
            session["messages"].append({"role": "assistant", "content": _blocks(final.content)})
            uses = [b for b in final.content if b.type == "tool_use"]
            if not uses:
                break
            results = []
            for use in uses:
                activity = {"type": "activity", "id": use.id, "tool": use.name, "label": ACTIVITY.get(use.name, ""), "status": "running"}
                if activity["label"]:
                    parts.append(activity)
                    yield {"type": "activity", **{k: activity[k] for k in ("id", "tool", "label", "status")}}
                queue: asyncio.Queue = asyncio.Queue()

                def progress(stage, message, done=0, total=0, _id=use.id):
                    queue.put_nowait({"type": "progress", "id": _id, "stage": stage, "message": message, "done": done, "total": total})

                task = asyncio.create_task(run_tool(owner_id, session, use.name, dict(use.input), progress))
                while not task.done():
                    try:
                        yield await asyncio.wait_for(queue.get(), timeout=0.5)
                    except TimeoutError:
                        continue
                while not queue.empty():
                    yield queue.get_nowait()
                try:
                    result, card = task.result()
                    activity["status"] = "done"
                    if card:
                        parts.append({"type": "card", **card})
                        yield {"type": "card", **card}
                    if use.name == "create_model":
                        yield {"type": "model", "model_id": session["model_id"], "title": session["title"]}
                    content, is_error = json.dumps(result, default=str)[:MAX_RESULT_CHARS], False
                except (service.NotFound, service.Conflict, ValueError, providers.ProviderError, probes.ProbeUnavailable) as exc:
                    activity["status"] = "error"
                    activity["error"] = str(exc)
                    content, is_error = f"Error: {exc}", True
                except Exception as exc:  # noqa: BLE001 -- surface to the wizard, keep the chat alive
                    log.exception("wizard tool %s failed", use.name)
                    activity["status"] = "error"
                    activity["error"] = "Internal error"
                    content, is_error = f"Error: internal failure in {use.name} ({type(exc).__name__})", True
                if activity["label"]:
                    yield {"type": "activity", "id": use.id, "tool": use.name, "label": activity["label"], "status": activity["status"], "error": activity.get("error")}
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": content, "is_error": is_error})
            session["messages"].append({"role": "user", "content": results})
        yield {"type": "done", "model_id": session["model_id"]}
    except Exception as exc:  # noqa: BLE001
        log.exception("wizard turn failed")
        message = "The wizard hit an error; try again." if not isinstance(exc, RuntimeError) else str(exc)
        parts.append({"type": "text", "text": f"\n\n_{message}_"})
        yield {"type": "error", "message": message}
    finally:
        _repair_dangling(session["messages"])
        await _save(session)


def _repair_dangling(messages: list[dict]) -> None:
    """A turn cut off mid-tool leaves tool_use without results; close them so the next turn is valid."""
    if not messages or messages[-1]["role"] != "assistant":
        return
    uses = [b for b in messages[-1]["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
    if uses:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": b["id"], "content": "Interrupted before it finished.", "is_error": True}
                    for b in uses
                ],
            }
        )
