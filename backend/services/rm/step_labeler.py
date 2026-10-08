"""Label every step of a trace: what the step is, not how well it went.

A trace is cut into chunks (a user message, an agent message, or a tool call
with its result). Each chunk is labeled in its own model call that carries the
whole conversation, so the label is made with full context. The rubric text
below is the instruction the model receives.
"""

from __future__ import annotations

import hashlib
import json

import httpx

from ...config import settings

API_URL = "https://api.openai.com/v1/responses"

RUBRIC = """You label one chunk of an agent conversation trace. You are given the full session transcript for context, then the id of the single chunk to label. Label only that chunk.

Rule zero: label only what's observable. "Agent answered 123558" is a label. "123558 is correct" is not. Never judge whether an answer is correct.

UNITS
- Chunk: one user message, one agent message, or one tool call paired with its result. Each chunk in the transcript has an id: u1, u2, ... for user chunks and a1, a2, ... for agent chunks.
- Segment: one user message plus every agent chunk until the next user message.
- Task: a new_request plus every following segment until the next new_request. Clarification rounds stay inside the same task.

USER CHUNKS: three fields

intent (pick one)
- new_request: new question not about the previous output. e.g. "ESN 11472702, need valve bridge pin"
- follow_up: new question that builds on the previous answer. e.g. "What's the install torque for it?"
- clarification_answer: answers a question the agent asked. e.g. "Exhaust valve bridge/crosshead pin"
- added_context: volunteers information without saying the agent was wrong. e.g. "It's a 1988 build if that helps"
- correction: says or implies the agent was wrong, and redirects. e.g. "No, that's intake, I need exhaust"
- requirement_change: changes what they want without saying the agent was wrong. e.g. "Actually, aftermarket only"
- repeat_request: asks the same thing again. e.g. asks for the pin again after getting an answer
- acknowledgment: adds nothing new. e.g. "ok", "thanks"

verdict (about the most recent agent output in this task)
- confirmed: explicitly says it's right, or acted on it ("yep that's it", "ordered")
- rejected: explicitly says it's wrong; any correction; any repeat_request
- partial: some parts right, some wrong ("pin's right, but I need 12")
- implicit_positive: "thanks", or moves on to a follow-up or unrelated request without complaint
- none: no signal: clarification answers, added context, or there is no earlier agent output for the verdict to refer to

sentiment: positive / neutral / negative.

verdict_target: the chunk id of the agent output the verdict refers to (the most recent agent output before this user chunk in the same task, or the previous task's final output when the user moves on to an unrelated request). null when verdict is none.

AGENT CHUNKS: type plus attributes

type (pick one)
- reasoning: internal thinking not shown to the user
- tool_call: any tool call, paired with its result
- clarifying_question: asks the user for information, including ask_user tools
- status_update: a user-facing interim message that's explicitly not final
- output: the user-facing response to the request

tool_call attributes
- effect: read (only retrieves information) / side_effect (creates, changes, sends or records something)
- result: data / empty (ran but returned nothing useful: no rows, no matches, empty list) / error
- If the chunk has no result recorded, set result to null and say so in note.

output attributes (set on a chunk of type output, and on a tool_call with is_output true)
- outcome: answer / partial_answer (some requested items answered) / not_found / error (an unrecovered failure reported to the user) / handoff (escalates or refuses)
- stance: asserted (no caveats) / hedged (states uncertainty or caveats explicitly). Read it from the text.
- coverage: "items addressed/items requested", e.g. "1/1" or "2/3"

is_output: true when this chunk delivers the user-facing response to the request. Always true for type output. For a tool_call, true only when the answer is delivered through that tool (such as submitting candidates). Otherwise false.

TIE-BREAKERS
- A user message that answers a question and says the agent was wrong is labeled correction.
- A tool error the agent recovered from goes only on the tool_call (result: error). It is not an output error.
- An answer delivered through a tool, such as submitting candidates, gets both labels: type tool_call with is_output true and the output attributes filled in.
- A message that gives a candidate but says it isn't done yet is a status_update.
- An ask_user style tool call is type clarifying_question, not tool_call.
- If you can't decide a field, use "other" for intent or type with a one-line note. Don't guess.

OUTPUT
Return one JSON object for the requested chunk.
- For a user chunk fill intent, verdict, verdict_target, sentiment; set every agent-only field to null.
- For an agent chunk fill type and is_output; fill effect and result only for type tool_call; fill outcome, stance, coverage only when is_output is true; set every user-only field to null.
- evidence: a short verbatim quote from the chunk (or its result) that supports the label. Keep it under 200 characters.
- note: null unless something needs a one-line explanation.
"""

N = ["string", "null"]
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "chunk_id",
        "actor",
        "intent",
        "verdict",
        "verdict_target",
        "sentiment",
        "type",
        "effect",
        "result",
        "is_output",
        "outcome",
        "stance",
        "coverage",
        "evidence",
        "note",
    ],
    "properties": {
        "chunk_id": {"type": "string"},
        "actor": {"type": "string", "enum": ["user", "agent"]},
        "intent": {
            "type": N,
            "enum": [
                "new_request",
                "follow_up",
                "clarification_answer",
                "added_context",
                "correction",
                "requirement_change",
                "repeat_request",
                "acknowledgment",
                "other",
                None,
            ],
        },
        "verdict": {
            "type": N,
            "enum": ["confirmed", "rejected", "partial", "implicit_positive", "none", None],
        },
        "verdict_target": {"type": N},
        "sentiment": {"type": N, "enum": ["positive", "neutral", "negative", None]},
        "type": {
            "type": N,
            "enum": [
                "reasoning",
                "tool_call",
                "clarifying_question",
                "status_update",
                "output",
                "other",
                None,
            ],
        },
        "effect": {"type": N, "enum": ["read", "side_effect", None]},
        "result": {"type": N, "enum": ["data", "empty", "error", None]},
        "is_output": {"type": ["boolean", "null"]},
        "outcome": {
            "type": N,
            "enum": ["answer", "partial_answer", "not_found", "error", "handoff", None],
        },
        "stance": {"type": N, "enum": ["asserted", "hedged", None]},
        "coverage": {"type": N},
        "evidence": {"type": "string"},
        "note": {"type": N},
    },
}


class LabelingError(RuntimeError):
    pass


def build_chunks(steps: list[dict]) -> list[dict]:
    """Trace steps -> chunks, each anchored on one step's index.

    A tool call is paired with the result that shares its tool_call_id.
    Consecutive identical user messages are one chunk (some uploaders store a
    message twice). System steps and reasoning are context, not chunks."""
    chunks: list[dict] = []
    paired: set[int] = set()
    users = agents = 0
    previous_user = None
    for i, step in enumerate(steps):
        if step["idx"] in paired or step["role"] in ("system", "tool"):
            continue
        if step["role"] == "user":
            if (
                previous_user is not None
                and previous_user["text"] == step["content"]
                and chunks
                and chunks[-1] is previous_user
            ):
                continue
            users += 1
            previous_user = {
                "chunk_id": f"u{users}",
                "actor": "user",
                "kind": "user_message",
                "idx": step["idx"],
                "text": step["content"],
            }
            chunks.append(previous_user)
            continue
        if (step.get("metadata") or {}).get("thinking"):
            continue
        agents += 1
        if step["tool_name"] is None:
            chunks.append(
                {
                    "chunk_id": f"a{agents}",
                    "actor": "agent",
                    "kind": "agent_message",
                    "idx": step["idx"],
                    "text": step["content"],
                }
            )
            continue
        result = next(
            (
                s
                for s in steps[i + 1 :]
                if s["role"] == "tool"
                and s["tool_call_id"] is not None
                and s["tool_call_id"] == step["tool_call_id"]
            ),
            None,
        )
        if result is not None:
            paired.add(result["idx"])
        chunks.append(
            {
                "chunk_id": f"a{agents}", "actor": "agent", "kind": "tool_call", "idx": step["idx"], "tool": step["tool_name"],
                "args": json.dumps(step["tool_input"] or {}, sort_keys=True), "result": None if result is None else result["content"],
            }
        )  # fmt: skip
    seen: dict[tuple, str] = {}
    for chunk in chunks:
        if chunk["kind"] == "tool_call":
            key = (chunk["tool"], chunk["args"])
            chunk["duplicate_of"] = seen.get(key)
            seen.setdefault(key, chunk["chunk_id"])
    return chunks


def clip(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    head = int(cap * 0.7)
    return f"{text[:head]}\n…[{len(text) - cap} characters omitted]…\n{text[-(cap - head) :]}"


def render_chunk(chunk: dict, cap: int | None = None) -> str:
    def body(text: str) -> str:
        return text if cap is None else clip(text, cap)

    if chunk["kind"] == "user_message":
        return f"[{chunk['chunk_id']}] USER message\n{chunk['text']}"
    if chunk["kind"] == "agent_message":
        return f"[{chunk['chunk_id']}] AGENT message\n{chunk['text']}"
    result = chunk["result"] if chunk["result"] is not None else "(no result recorded)"
    return f"[{chunk['chunk_id']}] AGENT tool call: {chunk['tool']}\nARGS: {body(chunk['args'])}\nRESULT: {body(result)}"


def render(chunks: list[dict], cap: int | None = None) -> str:
    return "\n\n".join(render_chunk(chunk, cap) for chunk in chunks)


async def label_chunk(
    client: httpx.AsyncClient, cache_key: str, transcript: str, chunk: dict
) -> dict:
    """One chunk's Rubric A label. The rubric and transcript are a cached prefix
    shared by every chunk of the trace; only the last line differs."""
    body = {
        "model": settings.STEP_LABEL_MODEL,
        "reasoning": {"effort": "low"},
        "prompt_cache_key": hashlib.sha1(cache_key.encode()).hexdigest()[:32],
        "prompt_cache_options": {"mode": "explicit"},
        "max_output_tokens": 2000,
        "input": [
            {"role": "system", "content": RUBRIC},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "SESSION TRANSCRIPT\n\n" + transcript,
                        "prompt_cache_breakpoint": {"mode": "explicit"},
                    }
                ],
            },
            {
                "role": "user",
                "content": f"Label chunk {chunk['chunk_id']} (actor: {chunk['actor']}).",
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "chunk_label",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    }
    try:
        response = await client.post(
            API_URL, json=body, headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        )
    except httpx.RequestError as exc:
        raise LabelingError(f"label request failed: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise LabelingError(f"label request returned {response.status_code}: {response.text[:200]}")
    try:
        text = "".join(
            part.get("text", "")
            for item in response.json()["output"]
            if item.get("type") == "message"
            for part in item["content"]
        )
        label = json.loads(text)
    except (KeyError, ValueError, TypeError) as exc:
        raise LabelingError("label response was not the expected JSON") from exc
    # Ids and facts we know from the trace itself are authoritative.
    label["chunk_id"], label["actor"] = chunk["chunk_id"], chunk["actor"]
    if chunk["kind"] == "tool_call":
        label["tool"] = chunk["tool"]
        label["duplicate_of"] = chunk["duplicate_of"]
        if chunk["result"] is None:
            label["result"] = None
    label["is_output"] = bool(label.get("is_output"))
    return label


def assign_tasks(chunks: list[dict], labels: dict[str, dict]) -> None:
    """A new task starts at each new_request (and at the first chunk)."""
    task = 0
    for chunk in chunks:
        label = labels[chunk["chunk_id"]]
        if task == 0 or (label["actor"] == "user" and label["intent"] == "new_request"):
            task += 1
        label["task_id"] = f"t{task}"
