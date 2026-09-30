"""Trace format adapters: every supported input format → CanonicalTrace.

The canonical shape and the list of formats are specified in
docs/reward-models/DESIGN.md ("Canonical trace format" and "Supported input
formats"). Everything here is a pure function over a string: no DB, no network.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .spans import TraceSpan, validate_spans

ROLES = {"system", "user", "assistant", "tool"}


class TraceFormatError(ValueError):
    pass


@dataclass
class CanonicalStep:
    role: str
    content: str
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_call_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class CanonicalTrace:
    external_id: str | None
    title: str | None
    metadata: dict
    steps: list[CanonicalStep]
    spans: list[TraceSpan] = field(default_factory=list)


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------


def _load_json(data: str) -> Any:
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        raise TraceFormatError(f"invalid JSON: {e}") from e


def _load_jsonl(data: str) -> list[Any]:
    records = []
    for line_number, line in enumerate(data.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise TraceFormatError(f"invalid JSON on line {line_number}: {e}") from e
    if not records:
        raise TraceFormatError("no records found")
    return records


def _sniff_json(data: str) -> Any:
    """Detectors must answer yes/no without raising, so undecodable input is None."""
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def _sniff_jsonl(data: str) -> list[Any] | None:
    try:
        return _load_jsonl(data)
    except TraceFormatError:
        return None


def _jsonl_dicts(data: str) -> list[dict] | None:
    records = _sniff_jsonl(data)
    if records is None:
        return None
    if not all(isinstance(r, dict) for r in records):
        return None
    return records


# ---------------------------------------------------------------------------
# Shared message helpers
# ---------------------------------------------------------------------------


def _block_text(block: Any) -> str:
    """Text of one content block. Non-text blocks (images, documents) are shown
    as a `[type]` marker so the reader knows something was there."""
    if isinstance(block, str):
        return block
    if block.get("type") in ("text", "input_text", "output_text", "summary_text"):
        return block["text"]
    return f"[{block['type']}]"


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_block_text(block) for block in content)
    raise TraceFormatError(f"unsupported content: {content!r:.200}")


def _json_text(value: Any) -> str:
    """Tool results and event bodies may be structured; steps hold strings."""
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _parse_arguments(arguments: Any) -> dict:
    """Tool arguments arrive as a JSON string (OpenAI, Codex, OTel) or an object."""
    if isinstance(arguments, dict):
        return arguments
    if arguments == "":
        return {}
    parsed = _load_json(arguments)
    if not isinstance(parsed, dict):
        raise TraceFormatError(f"tool arguments are not an object: {arguments!r:.200}")
    return parsed


def _tool_call_step(name: str, arguments: Any, call_id: str | None) -> CanonicalStep:
    return CanonicalStep(
        role="assistant",
        content="",
        tool_name=name,
        tool_input=_parse_arguments(arguments),
        tool_call_id=call_id,
    )


def _thinking_steps(text: str) -> list[CanonicalStep]:
    # Claude Code stores thinking with the text redacted (signature only), and
    # other sources log empty reasoning too; an empty step is noise for annotators.
    if not text:
        return []
    return [CanonicalStep(role="assistant", content=text, metadata={"thinking": True})]


def _block_steps(role: str, block: dict | str) -> list[CanonicalStep]:
    """Steps for one content block. Covers Anthropic blocks (`tool_use`,
    `tool_result`, `thinking`) and LangChain standard blocks (`tool_call`,
    `reasoning`); anything else is text or a `[type]` marker."""
    if isinstance(block, str):
        return [CanonicalStep(role=role, content=block)]

    kind = block["type"]
    if kind == "tool_use":
        return [_tool_call_step(block["name"], block["input"], block["id"])]
    if kind == "tool_call":
        return [_tool_call_step(block["name"], block["args"], block["id"])]
    if kind == "tool_result":
        metadata = {"is_error": True} if block.get("is_error") else {}
        return [
            CanonicalStep(
                role="tool",
                content=_content_text(block.get("content")),
                tool_call_id=block["tool_use_id"],
                metadata=metadata,
            )
        ]
    if kind == "thinking":
        return _thinking_steps(block["thinking"])
    if kind == "reasoning":
        return _thinking_steps(block["text"])
    if kind == "redacted_thinking":
        return []
    return [CanonicalStep(role=role, content=_block_text(block))]


def _fill_tool_names(steps: list[CanonicalStep]) -> list[CanonicalStep]:
    """Tool results usually carry only the call id; name them after the call."""
    names = {s.tool_call_id: s.tool_name for s in steps if s.role == "assistant" and s.tool_call_id}
    for step in steps:
        if step.role == "tool" and step.tool_name is None:
            step.tool_name = names.get(step.tool_call_id)
    return steps


def _merge_conversations(conversations: list[list[CanonicalStep]]) -> list[CanonicalStep]:
    """Join the messages of successive LLM calls in one trace.

    Each call in an agent loop re-sends the whole history as input, so when the
    steps gathered so far are a prefix of the next call's messages, only the new
    tail is appended. A call that doesn't extend the history (a separate
    conversation inside the same trace) is appended whole.

    Thinking steps are ignored in that comparison: OpenAI-style APIs don't
    re-send the model's reasoning, so the next call's input lacks it.
    """
    merged: list[CanonicalStep] = []
    for conversation in conversations:
        history = [s for s in merged if not _is_thinking(s)]
        replayed = _non_thinking_prefix_end(conversation, len(history))
        if [s for s in conversation[:replayed] if not _is_thinking(s)] == history:
            merged = merged + conversation[replayed:]
            continue
        merged = merged + conversation
    return _fill_tool_names(merged)


def _is_thinking(step: CanonicalStep) -> bool:
    return step.metadata.get("thinking", False)


def _non_thinking_prefix_end(steps: list[CanonicalStep], count: int) -> int:
    """Index just past the first `count` non-thinking steps."""
    seen = 0
    for index, step in enumerate(steps):
        if seen == count:
            return index
        if not _is_thinking(step):
            seen += 1
    return len(steps)


# ---------------------------------------------------------------------------
# stash
# ---------------------------------------------------------------------------


def _detect_stash(data: str) -> bool:
    records = _jsonl_dicts(data)
    if records is None:
        return False
    return isinstance(records[0].get("steps"), list)


def _parse_stash(data: str) -> list[CanonicalTrace]:
    traces = []
    for record in _load_jsonl(data):
        steps = [
            CanonicalStep(
                role=step["role"],
                content=step["content"],
                tool_name=step.get("tool_name"),
                tool_input=step.get("tool_input"),
                tool_call_id=step.get("tool_call_id"),
                metadata=step.get("metadata", {}),
            )
            for step in record["steps"]
        ]
        for step in steps:
            _with_timestamp([step], step.metadata.get("timestamp"))
        traces.append(
            CanonicalTrace(
                external_id=record.get("id"),
                title=record.get("title"),
                metadata=record.get("metadata", {}),
                steps=steps,
                spans=[TraceSpan.model_validate(span) for span in record.get("spans", [])],
            )
        )
    return traces


# ---------------------------------------------------------------------------
# openai_chat (also the message shape Langfuse, LangSmith and OTel events use)
# ---------------------------------------------------------------------------

_OPENAI_ROLES = {
    "system": "system",
    "developer": "system",
    "user": "user",
    "assistant": "assistant",
}


def _openai_tool_call_step(call: dict) -> CanonicalStep:
    """OpenAI nests the call under `function`; LangChain uses `name`/`args` at the top."""
    if "function" in call:
        return _tool_call_step(call["function"]["name"], call["function"]["arguments"], call["id"])
    return _tool_call_step(call["name"], call["args"], call["id"])


def _with_timestamp(steps: list[CanonicalStep], timestamp: str | None) -> list[CanonicalStep]:
    if timestamp is None:
        return steps
    try:
        parsed = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError) as exc:
        raise TraceFormatError("message timestamp must be an ISO 8601 datetime") from exc
    if parsed.tzinfo is None:
        raise TraceFormatError("message timestamp must include a timezone")
    for step in steps:
        step.metadata["timestamp"] = parsed.isoformat()
    return steps


def _openai_message_steps(message: dict) -> list[CanonicalStep]:
    role = message["role"]
    if role == "tool":
        return [
            CanonicalStep(
                role="tool",
                content=_content_text(message["content"]),
                tool_name=message.get("name"),
                tool_call_id=message["tool_call_id"],
            )
        ]

    if role not in _OPENAI_ROLES:
        raise TraceFormatError(f"unsupported message role: {role!r}")
    role = _OPENAI_ROLES[role]

    steps = []
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            steps.extend(_block_steps(role, block))
    elif content:
        steps.append(CanonicalStep(role=role, content=content))
    for call in message.get("tool_calls") or []:
        steps.append(_openai_tool_call_step(call))
    if not steps:
        steps.append(CanonicalStep(role=role, content=""))
    return steps


def _openai_steps(messages: list[dict]) -> list[CanonicalStep]:
    steps = [
        step
        for message in messages
        for step in _with_timestamp(_openai_message_steps(message), message.get("timestamp"))
    ]
    return _fill_tool_names(steps)


_ANTHROPIC_ONLY_BLOCKS = {"tool_use", "tool_result", "thinking", "redacted_thinking"}


def _looks_anthropic(record: dict) -> bool:
    if "system" in record:
        return True
    for message in record["messages"]:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if any(isinstance(b, dict) and b.get("type") in _ANTHROPIC_ONLY_BLOCKS for b in content):
            return True
    return False


def _detect_openai_chat(data: str) -> bool:
    whole = _sniff_json(data)
    if (
        isinstance(whole, list)
        and whole
        and all(isinstance(m, dict) and "role" in m for m in whole)
    ):
        return True
    records = _jsonl_dicts(data)
    if records is None:
        return False
    first = records[0]
    if not isinstance(first.get("messages"), list):
        return False
    return not _looks_anthropic(first)


def _parse_openai_chat(data: str) -> list[CanonicalTrace]:
    whole = _sniff_json(data)
    if isinstance(whole, list):
        return [CanonicalTrace(None, None, {}, _openai_steps(whole))]
    return [
        CanonicalTrace(None, None, {}, _openai_steps(record["messages"]))
        for record in _load_jsonl(data)
    ]


# ---------------------------------------------------------------------------
# anthropic_messages (also used by claude_code, whose lines carry the same blocks)
# ---------------------------------------------------------------------------


def _anthropic_message_steps(message: dict) -> list[CanonicalStep]:
    role = message["role"]
    if role not in ("user", "assistant"):
        raise TraceFormatError(f"unsupported Anthropic message role: {role!r}")
    content = message["content"]
    if isinstance(content, str):
        return [CanonicalStep(role=role, content=content)]
    steps = []
    for block in content:
        steps.extend(_block_steps(role, block))
    return steps


def _detect_anthropic_messages(data: str) -> bool:
    records = _jsonl_dicts(data)
    if records is None:
        return False
    messages = records[0].get("messages")
    if not isinstance(messages, list):
        return False
    return all(isinstance(m, dict) and m.get("role") in ("user", "assistant") for m in messages)


def _parse_anthropic_messages(data: str) -> list[CanonicalTrace]:
    traces = []
    for record in _load_jsonl(data):
        steps: list[CanonicalStep] = []
        system = record.get("system")
        if system:
            steps.append(CanonicalStep(role="system", content=_content_text(system)))
        for message in record["messages"]:
            steps.extend(_anthropic_message_steps(message))
        traces.append(CanonicalTrace(None, None, {}, _fill_tool_names(steps)))
    return traces


# ---------------------------------------------------------------------------
# otel: OTLP/JSON spans and log records, read with three conventions:
# - OpenInference: llm.input_messages.N.message.* / llm.output_messages.N.message.*
#   (github.com/Arize-ai/openinference, spec/semantic_conventions.md)
# - OTel GenAI: gen_ai.system_instructions / gen_ai.input.messages /
#   gen_ai.output.messages on spans or on a gen_ai.client.inference.operation.details
#   event, plus the older per-message events (gen_ai.user.message, gen_ai.choice, …)
#   (github.com/open-telemetry/semantic-conventions-genai)
# - OpenLLMetry: gen_ai.prompt.N.* / gen_ai.completion.N.* (github.com/traceloop/openllmetry)
# ---------------------------------------------------------------------------


def _otel_value(value: dict) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "bytesValue" in value:
        return value["bytesValue"]
    if "arrayValue" in value:
        return [_otel_value(v) for v in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return _otel_attributes(value["kvlistValue"].get("values", []))
    raise TraceFormatError(f"unsupported OTLP value: {value!r:.200}")


def _otel_attributes(key_values: list[dict]) -> dict[str, Any]:
    return {kv["key"]: _otel_value(kv["value"]) for kv in key_values}


def _indexed(attributes: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    """Group flattened attributes like `<prefix>.0.message.role` into one dict
    per index, keyed by the remainder (`message.role`), ordered by index."""
    groups: dict[int, dict[str, Any]] = {}
    for key, value in attributes.items():
        if not key.startswith(prefix + "."):
            continue
        index, _, rest = key[len(prefix) + 1 :].partition(".")
        groups.setdefault(int(index), {})[rest] = value
    return [groups[i] for i in sorted(groups)]


def _openinference_content_steps(role: str, content: dict[str, Any]) -> list[CanonicalStep]:
    kind = content["message_content.type"]
    if kind == "text":
        return [CanonicalStep(role=role, content=content["message_content.text"])]
    if kind == "reasoning":
        return _thinking_steps(content["message_content.text"])
    if kind == "tool_use":
        return [
            _tool_call_step(
                content["tool_call.function.name"],
                content.get("tool_call.function.arguments", ""),
                content.get("tool_call.id"),
            )
        ]
    return [CanonicalStep(role=role, content=f"[{kind}]")]


def _openinference_message_steps(fields: dict[str, Any]) -> list[CanonicalStep]:
    role = fields["message.role"]
    # A message with a tool_call_id is a tool result whatever its role:
    # openinference-instrumentation-anthropic reports Anthropic tool_result
    # blocks (which travel inside user messages) as role "user".
    if role == "tool" or "message.tool_call_id" in fields:
        return [
            CanonicalStep(
                role="tool",
                content=fields["message.content"],
                tool_name=fields.get("message.name"),
                tool_call_id=fields.get("message.tool_call_id"),
            )
        ]
    if role not in _OPENAI_ROLES:
        raise TraceFormatError(f"unsupported OpenInference message role: {role!r}")
    role = _OPENAI_ROLES[role]

    steps = []
    for content in _indexed(fields, "message.contents"):
        steps.extend(_openinference_content_steps(role, content))
    if fields.get("message.content"):
        steps.append(CanonicalStep(role=role, content=fields["message.content"]))
    # Some instrumentations (openinference-instrumentation-anthropic) report each
    # tool call twice: as a `tool_use` part in message.contents, which keeps its
    # order among the text parts, and again in message.tool_calls. Keep the first.
    content_call_ids = {s.tool_call_id for s in steps if s.tool_call_id is not None}
    for call in _indexed(fields, "message.tool_calls"):
        if call.get("tool_call.id") in content_call_ids:
            continue
        steps.append(
            _tool_call_step(
                call["tool_call.function.name"],
                call.get("tool_call.function.arguments", ""),
                call.get("tool_call.id"),
            )
        )
    if not steps:
        steps.append(CanonicalStep(role=role, content=""))
    return steps


def _openllmetry_message(fields: dict[str, Any]) -> dict:
    """Rebuild an OpenAI-style message from `gen_ai.prompt.N.*` / `gen_ai.completion.N.*` fields."""
    message: dict[str, Any] = {"role": fields["role"], "content": fields.get("content")}
    if "tool_call_id" in fields:
        message["tool_call_id"] = fields["tool_call_id"]
    tool_calls = _indexed(fields, "tool_calls")
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": call.get("id"),
                "function": {"name": call["name"], "arguments": call.get("arguments", "")},
            }
            for call in tool_calls
        ]
    return message


def _gen_ai_part_steps(role: str, part: dict) -> list[CanonicalStep]:
    """Steps for one message part of the GenAI message JSON schemas
    (model/gen-ai/gen-ai-input-messages.json and gen-ai-output-messages.json)."""
    kind = part["type"]
    if kind == "text":
        return [CanonicalStep(role=role, content=part["content"])]
    if kind == "reasoning":
        return _thinking_steps(part["content"])
    if kind == "tool_call":
        # `arguments` is optional in the schema; a call without it has no input.
        if "arguments" not in part:
            return [
                CanonicalStep(
                    role="assistant",
                    content="",
                    tool_name=part["name"],
                    tool_call_id=part.get("id"),
                )
            ]
        return [_tool_call_step(part["name"], part["arguments"], part.get("id"))]
    if kind == "tool_call_response":
        return [
            CanonicalStep(
                role="tool", content=_json_text(part["response"]), tool_call_id=part.get("id")
            )
        ]
    if kind == "server_tool_call":
        return [_tool_call_step(part["name"], part["server_tool_call"], part.get("id"))]
    if kind == "server_tool_call_response":
        return [
            CanonicalStep(
                role="tool",
                content=_json_text(part["server_tool_call_response"]),
                tool_call_id=part.get("id"),
            )
        ]
    return [CanonicalStep(role=role, content=f"[{kind}]")]


def _gen_ai_json(value: Any) -> Any:
    """GenAI message attributes SHOULD be structured but MAY be a JSON string."""
    if isinstance(value, str):
        return _load_json(value)
    return value


def _gen_ai_messages_steps(attributes: dict[str, Any]) -> list[CanonicalStep]:
    """Each of the three attributes is optional; a span may carry any of them."""
    steps = []
    if "gen_ai.system_instructions" in attributes:
        for part in _gen_ai_json(attributes["gen_ai.system_instructions"]):
            steps.extend(_gen_ai_part_steps("system", part))
    for key in ("gen_ai.input.messages", "gen_ai.output.messages"):
        if key not in attributes:
            continue
        for message in _gen_ai_json(attributes[key]):
            for part in message["parts"]:
                steps.extend(_gen_ai_part_steps(message["role"], part))
    return steps


_GEN_AI_MESSAGE_KEYS = (
    "gen_ai.system_instructions",
    "gen_ai.input.messages",
    "gen_ai.output.messages",
)


def _otel_attribute_steps(attributes: dict[str, Any]) -> list[CanonicalStep]:
    """The conversation carried by one span's (or details event's) attributes, or []."""
    if any(k.startswith("llm.input_messages.") for k in attributes):
        messages = _indexed(attributes, "llm.input_messages")
        messages = messages + _indexed(attributes, "llm.output_messages")
        steps = [step for m in messages for step in _openinference_message_steps(m)]
        return _fill_tool_names(steps)
    if any(k in attributes for k in _GEN_AI_MESSAGE_KEYS):
        return _fill_tool_names(_gen_ai_messages_steps(attributes))
    if any(k.startswith("gen_ai.prompt.") for k in attributes):
        messages = _indexed(attributes, "gen_ai.prompt") + _indexed(attributes, "gen_ai.completion")
        return _openai_steps([_openllmetry_message(m) for m in messages])
    return []


def _gen_ai_event_message(event_name: str, body: dict) -> dict:
    """An OpenAI-style message from one deprecated per-message GenAI event.
    The body fields are defined in the semantic-conventions repo,
    model/gen-ai/deprecated/events-deprecated.yaml."""
    if event_name == "gen_ai.choice":
        message = dict(body["message"])
        message["role"] = "assistant"
    elif event_name == "gen_ai.tool.message":
        message = {"role": "tool", "content": body.get("content"), "tool_call_id": body["id"]}
    else:
        message = dict(body)
        message["role"] = event_name.removeprefix("gen_ai.").removesuffix(".message")
    if message.get("content") is not None:
        message["content"] = _json_text(message["content"])
    return message


_GEN_AI_MESSAGE_EVENTS = {
    "gen_ai.system.message",
    "gen_ai.user.message",
    "gen_ai.assistant.message",
    "gen_ai.tool.message",
    "gen_ai.choice",
}
_GEN_AI_DETAILS_EVENT = "gen_ai.client.inference.operation.details"


def _otlp_payloads(data: str) -> list[dict]:
    """One OTLP/JSON export request, or the OTel Collector file exporter's JSONL
    (one export request per line)."""
    whole = _sniff_json(data)
    payloads = [whole] if whole is not None else _load_jsonl(data)
    for payload in payloads:
        if not isinstance(payload, dict) or not (
            "resourceSpans" in payload or "resourceLogs" in payload
        ):
            raise TraceFormatError(
                "expected OTLP export requests with resourceSpans or resourceLogs"
            )
    return payloads


def _otel_calls(payloads: list[dict]) -> dict[str, list[tuple[int, str, list[CanonicalStep]]]]:
    """Every LLM call in the payloads, as (start time in ns, steps), grouped by trace id."""
    calls: dict[str, list[tuple[int, str, list[CanonicalStep]]]] = {}
    event_groups: dict[tuple[str, str], list[tuple[int, dict]]] = {}

    for payload in payloads:
        for resource_spans in payload.get("resourceSpans", []):
            for scope_spans in resource_spans.get("scopeSpans", []):
                for span in scope_spans.get("spans", []):
                    steps = _otel_attribute_steps(_otel_attributes(span.get("attributes", [])))
                    if steps:
                        entry = (int(span["startTimeUnixNano"]), span["spanId"], steps)
                        calls.setdefault(span["traceId"], []).append(entry)

        for resource_logs in payload.get("resourceLogs", []):
            for scope_logs in resource_logs.get("scopeLogs", []):
                for record in scope_logs.get("logRecords", []):
                    attributes = _otel_attributes(record.get("attributes", []))
                    # OTLP 1.5 added the top-level eventName field; earlier SDKs
                    # wrote the name as the event.name attribute.
                    event_name = record.get("eventName") or attributes.get("event.name")
                    if event_name not in _GEN_AI_MESSAGE_EVENTS | {_GEN_AI_DETAILS_EVENT}:
                        continue
                    if not record.get("traceId"):
                        raise TraceFormatError(f"{event_name} log record has no traceId")
                    time = int(record["observedTimeUnixNano"])
                    if event_name == _GEN_AI_DETAILS_EVENT:
                        steps = _otel_attribute_steps(attributes)
                        calls.setdefault(record["traceId"], []).append(
                            (time, record["spanId"], steps)
                        )
                        continue
                    message = _gen_ai_event_message(event_name, _otel_value(record["body"]))
                    key = (record["traceId"], record["spanId"])
                    event_groups.setdefault(key, []).append((time, message))

    # The per-message events of one span together make up that span's LLM call.
    for (trace_id, span_id), timed_messages in event_groups.items():
        start = min(time for time, _ in timed_messages)
        steps = _openai_steps([message for _, message in timed_messages])
        calls.setdefault(trace_id, []).append((start, span_id, steps))
    return calls


def _detect_otel(data: str) -> bool:
    whole = _sniff_json(data)
    payloads = [whole] if whole is not None else _jsonl_dicts(data)
    if not payloads or not isinstance(payloads[0], dict):
        return False
    return "resourceSpans" in payloads[0] or "resourceLogs" in payloads[0]


def _parse_otel(data: str) -> list[CanonicalTrace]:
    payloads = _otlp_payloads(data)
    spans_by_trace: dict[str, list[TraceSpan]] = {}
    for payload in payloads:
        for resource in payload.get("resourceSpans", []):
            for scope in resource.get("scopeSpans", []):
                for raw in scope.get("spans", []):
                    attributes = _otel_attributes(raw.get("attributes", []))
                    span = TraceSpan(
                        id=raw["spanId"],
                        parent_id=raw.get("parentSpanId"),
                        name=raw["name"],
                        kind=attributes.get("openinference.span.kind"),
                        start_ns=str(raw["startTimeUnixNano"]),
                        end_ns=str(raw["endTimeUnixNano"]),
                        input=_json_text(attributes["input.value"])
                        if "input.value" in attributes
                        else None,
                        output=_json_text(attributes["output.value"])
                        if "output.value" in attributes
                        else None,
                    )
                    spans_by_trace.setdefault(raw["traceId"], []).append(span)

    traces = []
    for trace_id, calls in _otel_calls(payloads).items():
        calls.sort(key=lambda call: call[0])
        steps = _merge_conversations([messages for _, _, messages in calls])
        indices = {id(step): index for index, step in enumerate(steps)}
        spans = spans_by_trace.get(trace_id, [])
        by_id = {span.id: span for span in spans}
        for _, span_id, messages in calls:
            if span_id in by_id:
                by_id[span_id].step_indices = [
                    indices[id(step)] for step in messages if id(step) in indices
                ]
        traces.append(CanonicalTrace(trace_id, None, {}, steps, spans))
    return traces


def otel_spans_have_messages(spans: list[dict]) -> bool:
    """Whether any OTLP/JSON span carries an LLM conversation.

    A live trace's spans arrive in batches; until an LLM span is among them
    there is nothing to build a trace from yet, and that is not an error.
    """
    return any(
        _otel_attribute_steps(_otel_attributes(span.get("attributes", []))) for span in spans
    )


# ---------------------------------------------------------------------------
# langfuse: GET /api/public/traces/{traceId} responses (TraceWithFullDetails in
# the Langfuse OpenAPI spec), one object or a JSON array of them
# ---------------------------------------------------------------------------


def _langfuse_traces(whole: Any) -> list[dict] | None:
    if isinstance(whole, dict):
        return [whole]
    if isinstance(whole, list):
        return whole
    return None


def _detect_langfuse(data: str) -> bool:
    traces = _langfuse_traces(_sniff_json(data))
    if not traces:
        return False
    return all(isinstance(t, dict) and isinstance(t.get("observations"), list) for t in traces)


def _langfuse_generation_steps(generation: dict) -> list[CanonicalStep]:
    """A generation's input is a message list (bare or under `messages`), its
    output an assistant message or plain text."""
    inputs = generation["input"]
    if isinstance(inputs, dict):
        inputs = inputs["messages"]
    output = generation["output"]
    if isinstance(output, str):
        output = {"role": "assistant", "content": output}
    messages = inputs + ([output] if output else [])
    return _openai_steps(messages)


def _parse_langfuse(data: str) -> list[CanonicalTrace]:
    traces = []
    for trace in _langfuse_traces(_load_json(data)):
        observations = sorted(trace["observations"], key=lambda o: o["startTime"])
        # Same reasoning as OTel: tool observations repeat what the generations'
        # messages already carry, so only generations are read.
        conversations = [
            _langfuse_generation_steps(o) for o in observations if o["type"] == "GENERATION"
        ]
        traces.append(
            CanonicalTrace(
                external_id=trace["id"],
                title=trace["name"],
                metadata={},
                steps=_merge_conversations(conversations),
            )
        )
    return traces


# ---------------------------------------------------------------------------
# langsmith: runs in the LangSmith run data format
# (docs.langchain.com/langsmith/run-data-format), one per JSONL line
# ---------------------------------------------------------------------------

_LANGCHAIN_ROLES = {
    "human": "user",
    "ai": "assistant",
    "system": "system",
    "tool": "tool",
    "HumanMessage": "user",
    "AIMessage": "assistant",
    "AIMessageChunk": "assistant",
    "SystemMessage": "system",
    "ToolMessage": "tool",
}


def _langchain_message(message: dict) -> dict:
    """Normalize a LangSmith message to an OpenAI-style message.

    LangSmith stores messages three ways: role/content dicts (the documented
    LLM run format, and what `wrap_openai` logs), LangChain-serialized objects
    (`{"lc": 1, "id": [..., "AIMessage"], "kwargs": {...}}`), and
    `{"type": "ai", "data": {...}}` / `{"type": "ai", "content": ...}` dicts.
    """
    if "role" in message:
        return message
    if message.get("lc") == 1:
        kind = message["id"][-1]
        fields = message["kwargs"]
    elif "data" in message:
        kind = message["type"]
        fields = message["data"]
    else:
        kind = message["type"]
        fields = message
    if kind not in _LANGCHAIN_ROLES:
        raise TraceFormatError(f"unsupported LangChain message type: {kind!r}")

    normalized = {"role": _LANGCHAIN_ROLES[kind], "content": fields.get("content")}
    for key in ("tool_call_id", "tool_calls", "name"):
        if fields.get(key):
            normalized[key] = fields[key]
    return normalized


def _langsmith_output_messages(outputs: Any) -> list[dict]:
    """The documented LLM run output shapes (docs.langchain.com/langsmith/log-llm-trace)
    plus LangChain's `generations`."""
    if not outputs:
        return []
    if isinstance(outputs, list):
        role, content = outputs
        return [{"role": role, "content": content}]
    if "generations" in outputs:
        generations = outputs["generations"]
        # LangChain logs a batch: one list of generations per prompt. One run is one call.
        if generations and isinstance(generations[0], list):
            generations = generations[0]
        return [g["message"] for g in generations]
    if "choices" in outputs:
        return [c["message"] for c in outputs["choices"]]
    if "messages" in outputs:
        return outputs["messages"]
    if "role" in outputs:
        return [outputs]
    raise TraceFormatError(f"unsupported LangSmith llm outputs with keys {sorted(outputs)}")


def _langsmith_llm_messages(run: dict) -> list[dict]:
    inputs = run["inputs"]["messages"]
    # LangChain chat models log a batch: a list of message lists. One run is one call.
    if inputs and isinstance(inputs[0], list):
        inputs = inputs[0]
    outputs = _langsmith_output_messages(run.get("outputs"))
    return [_langchain_message(m) for m in inputs + outputs]


def _detect_langsmith(data: str) -> bool:
    records = _jsonl_dicts(data)
    if records is None:
        return False
    return all("run_type" in r and "trace_id" in r for r in records)


def _parse_langsmith(data: str) -> list[CanonicalTrace]:
    runs_by_trace: dict[str, list[dict]] = {}
    for run in _load_jsonl(data):
        runs_by_trace.setdefault(run["trace_id"], []).append(run)

    traces = []
    for trace_id, runs in runs_by_trace.items():
        runs.sort(key=lambda r: r["start_time"])
        # Tool and chain runs are skipped for the same reason as OTel tool spans.
        conversations = [
            _openai_steps(_langsmith_llm_messages(r)) for r in runs if r["run_type"] == "llm"
        ]
        traces.append(
            CanonicalTrace(
                external_id=trace_id,
                title=None,
                metadata={},
                steps=_merge_conversations(conversations),
            )
        )
    return traces


# ---------------------------------------------------------------------------
# claude_code
# ---------------------------------------------------------------------------


def _detect_claude_code(data: str) -> bool:
    records = _jsonl_dicts(data)
    if records is None:
        return False
    return any(r.get("type") in ("user", "assistant") and "sessionId" in r for r in records)


def _is_claude_code_conversation_line(record: dict) -> bool:
    """Only `user` / `assistant` lines are the conversation. Everything else in
    the file (attachments, titles, mode changes, file snapshots, hook `system`
    lines) is Claude Code's own bookkeeping, never sent to the model as a turn.
    Among user/assistant lines we also drop:
    - isMeta: harness-injected text (command caveats, skill bodies) the user didn't type.
    - isSidechain: a subagent's separate conversation interleaved in older files.
    - isCompactSummary: a summary of earlier lines that are still in the file.
    - isApiErrorMessage: a synthetic error shown in the UI, not a model reply.
    """
    if record.get("type") not in ("user", "assistant"):
        return False
    for flag in ("isMeta", "isSidechain", "isCompactSummary", "isApiErrorMessage"):
        if record.get(flag):
            return False
    return True


def _parse_claude_code(data: str) -> list[CanonicalTrace]:
    records = _load_jsonl(data)
    steps: list[CanonicalStep] = []
    for record in records:
        if not _is_claude_code_conversation_line(record):
            continue
        steps.extend(
            _with_timestamp(_anthropic_message_steps(record["message"]), record.get("timestamp"))
        )

    session_ids = [r["sessionId"] for r in records if "sessionId" in r]
    titles = [r["aiTitle"] for r in records if r.get("type") == "ai-title"]
    first = next(r for r in records if "cwd" in r)
    return [
        CanonicalTrace(
            external_id=session_ids[0],
            # The title is regenerated as the session goes on; the last one is current.
            title=titles[-1] if titles else None,
            metadata={"cwd": first["cwd"], "git_branch": first.get("gitBranch")},
            steps=_fill_tool_names(steps),
        )
    ]


# ---------------------------------------------------------------------------
# codex
# ---------------------------------------------------------------------------

_CODEX_ROLES = {"developer": "system", "system": "system", "user": "user", "assistant": "assistant"}


def _codex_item_steps(item: dict) -> list[CanonicalStep]:
    kind = item["type"]
    if kind == "message":
        return [
            CanonicalStep(role=_CODEX_ROLES[item["role"]], content=_content_text(item["content"]))
        ]
    if kind == "function_call":
        return [
            CanonicalStep(
                role="assistant",
                content="",
                tool_name=item["name"],
                tool_input=_parse_arguments(item["arguments"]),
                tool_call_id=item["call_id"],
            )
        ]
    if kind == "custom_tool_call":
        # Custom (freeform) tools take raw text, not JSON arguments.
        return [
            CanonicalStep(
                role="assistant",
                content="",
                tool_name=item["name"],
                tool_input={"input": item["input"]},
                tool_call_id=item["call_id"],
            )
        ]
    if kind in ("function_call_output", "custom_tool_call_output"):
        return [
            CanonicalStep(
                role="tool",
                content=_content_text(item["output"]),
                tool_call_id=item["call_id"],
            )
        ]
    if kind == "reasoning":
        # Only the summary is readable; the full reasoning is encrypted.
        text = "\n".join(_block_text(s) for s in item.get("summary") or [])
        if not text:
            return []
        return [CanonicalStep(role="assistant", content=text, metadata={"thinking": True})]
    # Other response items (web_search_call, local_shell_call, …) carry no text
    # an annotator can judge.
    return []


def _detect_codex(data: str) -> bool:
    records = _jsonl_dicts(data)
    if records is None:
        return False
    return any(
        r.get("type") in ("session_meta", "response_item") and "payload" in r for r in records
    )


def _parse_codex(data: str) -> list[CanonicalTrace]:
    records = _load_jsonl(data)
    # Only `response_item` lines are the model-visible conversation; `event_msg`,
    # `turn_context`, token counts and `compacted` are Codex bookkeeping that
    # restate or annotate those items.
    steps: list[CanonicalStep] = []
    for record in records:
        if record["type"] != "response_item":
            continue
        steps.extend(_with_timestamp(_codex_item_steps(record["payload"]), record.get("timestamp")))

    meta = next(r["payload"] for r in records if r["type"] == "session_meta")
    return [
        CanonicalTrace(
            external_id=meta["id"],
            title=None,
            metadata={"cwd": meta.get("cwd"), "cli_version": meta.get("cli_version")},
            steps=_fill_tool_names(steps),
        )
    ]


# ---------------------------------------------------------------------------
# Registry and entry points
# ---------------------------------------------------------------------------

FORMATS: list[tuple[str, str, Callable[[str], bool], Callable[[str], list[CanonicalTrace]]]] = [
    ("stash", "Stash Trace Format JSONL, one trace per line", _detect_stash, _parse_stash),
    (
        "openai_chat",
        'OpenAI chat JSONL of {"messages": [...]} (fine-tuning format) or a JSON array of messages',
        _detect_openai_chat,
        _parse_openai_chat,
    ),
    (
        "anthropic_messages",
        'Anthropic Messages JSONL of {"system": ..., "messages": [...]}',
        _detect_anthropic_messages,
        _parse_anthropic_messages,
    ),
    (
        "otel",
        "OTLP/JSON spans and logs (one export, or Collector file-exporter JSONL) read with the"
        " OpenInference, OTel GenAI and OpenLLMetry conventions, one trace per traceId",
        _detect_otel,
        _parse_otel,
    ),
    (
        "langfuse",
        "Langfuse trace JSON from GET /api/public/traces/{traceId}, one object or an array",
        _detect_langfuse,
        _parse_langfuse,
    ),
    (
        "langsmith",
        "LangSmith run export JSONL, one trace per trace_id",
        _detect_langsmith,
        _parse_langsmith,
    ),
    (
        "claude_code",
        "Claude Code session transcript JSONL (~/.claude/projects/**/*.jsonl), one trace per file",
        _detect_claude_code,
        _parse_claude_code,
    ),
    (
        "codex",
        "Codex CLI rollout JSONL (~/.codex/sessions/**/rollout-*.jsonl), one trace per file",
        _detect_codex,
        _parse_codex,
    ),
]

_FORMATS_BY_NAME = {name: (detect, parse) for name, _, detect, parse in FORMATS}


def list_formats() -> list[dict]:
    return [{"name": name, "description": description} for name, description, _, _ in FORMATS]


def _resolve_format(data: str, format: str) -> str:
    if format != "auto":
        if format not in _FORMATS_BY_NAME:
            known = ", ".join(_FORMATS_BY_NAME)
            raise TraceFormatError(f"unknown format {format!r}; expected auto or one of: {known}")
        return format
    for name, _, detect, _ in FORMATS:
        if detect(data):
            return name
    tried = ", ".join(_FORMATS_BY_NAME)
    raise TraceFormatError(f"could not detect the trace format; tried: {tried}")


def _validate(trace: CanonicalTrace, index: int) -> None:
    where = f"trace {index} ({trace.external_id})" if trace.external_id else f"trace {index}"
    try:
        validate_spans(trace.spans, len(trace.steps))
    except ValueError as exc:
        raise TraceFormatError(f"{where}: {exc}") from exc
    if not trace.steps:
        raise TraceFormatError(f"{where} has no steps")
    for step_index, step in enumerate(trace.steps):
        if step.role not in ROLES:
            raise TraceFormatError(f"{where} step {step_index}: invalid role {step.role!r}")
        if not isinstance(step.content, str):
            raise TraceFormatError(f"{where} step {step_index}: content must be a string")
        if step.tool_input is not None and not isinstance(step.tool_input, dict):
            raise TraceFormatError(f"{where} step {step_index}: tool_input must be an object")


def parse_traces(data: str, format: str) -> tuple[str, list[CanonicalTrace]]:
    """Parse `data` in `format` (or `auto`) and return (resolved format name, traces)."""
    name = _resolve_format(data, format)
    _, parse = _FORMATS_BY_NAME[name]
    try:
        traces = parse(data)
    except TraceFormatError as e:
        raise TraceFormatError(f"could not parse as {name}: {e}") from e
    # A payload of the wrong shape surfaces as a missing key or wrong type deep
    # in a parser; report it as a format error naming the format.
    except (KeyError, TypeError, AttributeError, IndexError, ValueError, StopIteration) as e:
        raise TraceFormatError(f"could not parse as {name}: {type(e).__name__}: {e}") from e

    if not traces:
        raise TraceFormatError(f"no traces found in {name} input")
    for index, trace in enumerate(traces):
        _validate(trace, index)
    return name, traces
