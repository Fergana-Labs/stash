"""Format adapters turn every supported trace format into the canonical steps
that annotators comment on and the reward model trains on. A wrong role, a
dropped tool result, or a duplicated turn here silently corrupts every label
built on top, so each format is checked step by step."""

from pathlib import Path

import pytest

from backend.services.rm.adapters import (
    FORMATS,
    TraceFormatError,
    list_formats,
    parse_traces,
)

FIXTURES = Path(__file__).parent / "fixtures" / "rm_formats"

FIXTURE_FORMATS = [
    ("stash.jsonl", "stash"),
    ("openai_chat.jsonl", "openai_chat"),
    ("openai_chat_array.json", "openai_chat"),
    ("anthropic_messages.jsonl", "anthropic_messages"),
    ("otel.json", "otel"),
    ("otel_genai.jsonl", "otel"),
    ("otel_openinference_anthropic.json", "otel"),
    ("langfuse.json", "langfuse"),
    ("langsmith.jsonl", "langsmith"),
    ("claude_code.jsonl", "claude_code"),
    ("codex.jsonl", "codex"),
]


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def _roles(trace) -> list[str]:
    return [step.role for step in trace.steps]


def test_list_formats_matches_design_doc():
    names = [f["name"] for f in list_formats()]
    assert names == [
        "stash",
        "openai_chat",
        "anthropic_messages",
        "otel",
        "langfuse",
        "langsmith",
        "claude_code",
        "codex",
    ]
    assert all(f["description"] for f in list_formats())


@pytest.mark.parametrize("fixture,expected", FIXTURE_FORMATS)
def test_auto_detects_each_format(fixture, expected):
    name, _ = parse_traces(_read(fixture), "auto")
    assert name == expected


@pytest.mark.parametrize("fixture,expected", FIXTURE_FORMATS)
def test_explicit_format_matches_auto(fixture, expected):
    assert parse_traces(_read(fixture), expected) == parse_traces(_read(fixture), "auto")


def test_every_format_has_a_fixture():
    covered = {expected for _, expected in FIXTURE_FORMATS}
    assert covered == {name for name, _, _, _ in FORMATS}


def test_stash():
    _, traces = parse_traces(_read("stash.jsonl"), "stash")
    assert len(traces) == 2
    trace = traces[0]
    assert trace.external_id == "refund-1182"
    assert trace.title == "Refund request for order 1182"
    assert trace.metadata == {"agent": "support-bot"}
    assert _roles(trace) == ["system", "user", "assistant", "tool", "assistant"]
    call = trace.steps[2]
    assert (call.tool_name, call.tool_input, call.tool_call_id) == (
        "lookup_order",
        {"order_id": "1182"},
        "call_1",
    )
    assert traces[1].external_id is None


def test_openai_chat_tool_calls_and_results():
    _, traces = parse_traces(_read("openai_chat.jsonl"), "openai_chat")
    assert len(traces) == 2
    trace = traces[0]
    assert _roles(trace) == ["system", "user", "assistant", "tool", "assistant"]
    call, result = trace.steps[2], trace.steps[3]
    assert call.content == ""
    assert call.tool_name == "get_weather"
    # Arguments arrive as a JSON string and must become an object.
    assert call.tool_input == {"city": "Paris"}
    # The tool message has no name; it is named after its call.
    assert (result.tool_name, result.tool_call_id, result.content) == (
        "get_weather",
        "call_w1",
        "18C, cloudy",
    )
    # List-of-parts content is flattened to text.
    assert traces[1].steps[0].content == "Say hi"


def test_openai_chat_json_array_is_one_trace_and_developer_is_system():
    _, traces = parse_traces(_read("openai_chat_array.json"), "openai_chat")
    assert len(traces) == 1
    assert _roles(traces[0]) == ["system", "user", "assistant"]


def test_anthropic_messages_blocks():
    _, traces = parse_traces(_read("anthropic_messages.jsonl"), "anthropic_messages")
    steps = traces[0].steps
    assert _roles(traces[0]) == [
        "system",
        "user",
        "assistant",  # thinking
        "assistant",  # text
        "assistant",  # tool_use
        "tool",
        "assistant",
    ]
    assert steps[2].metadata == {"thinking": True}
    assert (steps[4].tool_name, steps[4].tool_input, steps[4].tool_call_id) == (
        "bash",
        {"command": "ls"},
        "toolu_1",
    )
    # A tool_result lives inside a user message but is the tool's turn.
    assert (steps[5].tool_name, steps[5].tool_call_id, steps[5].content) == (
        "bash",
        "toolu_1",
        "a.py\nb.py",
    )


def test_otel_openinference_merges_llm_spans_without_duplicating_history():
    _, traces = parse_traces(_read("otel.json"), "otel")
    by_id = {t.external_id: t for t in traces}
    agent = by_id["5b8efff798038103d269b633813fc60c"]
    # Two LLM spans (the second re-sends the first's history, minus the
    # reasoning) plus a tool span must read as one conversation, each turn
    # once, in start-time order.
    assert _roles(agent) == ["system", "user", "assistant", "assistant", "tool", "assistant"]
    # message.contents: a reasoning part, then a tool_use part.
    assert agent.steps[2].content == "I need flight options first."
    assert agent.steps[2].metadata == {"thinking": True}
    assert agent.steps[3].tool_name == "search_flights"
    assert agent.steps[3].tool_input == {"to": "FCO"}
    assert (agent.steps[4].tool_name, agent.steps[4].content) == ("search_flights", "AZ610 at 9am")
    assert agent.steps[5].content == "Book AZ610 departing 9am."

    openllmetry = by_id["0af7651916cd43dd8448eb211c80319c"]
    assert [(s.role, s.content) for s in openllmetry.steps] == [
        ("user", "Translate 'hello' to French."),
        ("assistant", "Bonjour"),
    ]


def test_otel_openinference_anthropic_real_span():
    """A real span from openinference-instrumentation-anthropic. It reports each
    tool call twice (message.contents and message.tool_calls) and the tool
    result as a "user" message with a tool_call_id; neither may leak through as
    a duplicate call or a user turn."""
    _, traces = parse_traces(_read("otel_openinference_anthropic.json"), "otel")
    assert len(traces) == 1
    steps = traces[0].steps
    assert _roles(traces[0]) == ["system", "user", "assistant", "assistant", "tool", "assistant"]
    assert steps[2].content.startswith("I'm sorry to hear")
    call, result = steps[3], steps[4]
    assert (call.tool_name, call.tool_input, call.tool_call_id) == (
        "lookup_order",
        {"order_id": "A7731"},
        "toolu_01EjS4pd5jHtAxZcCEf9EPXR",
    )
    assert (result.tool_name, result.tool_call_id) == (
        "lookup_order",
        "toolu_01EjS4pd5jHtAxZcCEf9EPXR",
    )
    assert '"delivered_days_ago": 41' in result.content


def test_otel_gen_ai_message_attributes_structured_and_json_string():
    _, traces = parse_traces(_read("otel_genai.jsonl"), "otel")
    by_id = {t.external_id: t for t in traces}
    weather = by_id["4bf92f3577b34da6a3ce929d0e0e4736"]
    # First span: structured (kvlist) attributes. Second span: the same
    # attributes as JSON strings, re-sending the history. Tool span skipped.
    assert [(s.role, s.content) for s in weather.steps] == [
        ("system", "You are a weather assistant."),
        ("user", "Weather in Paris?"),
        ("assistant", "Call the weather tool."),
        ("assistant", ""),
        ("tool", "rainy, 57°F"),
        ("assistant", "It's rainy and 57°F in Paris."),
    ]
    call = weather.steps[3]
    assert (call.tool_name, call.tool_input, call.tool_call_id) == (
        "get_weather",
        {"location": "Paris"},
        "call_VSPy",
    )
    assert weather.steps[4].tool_name == "get_weather"


def test_otel_gen_ai_log_events():
    _, traces = parse_traces(_read("otel_genai.jsonl"), "otel")
    by_id = {t.external_id: t for t in traces}
    # Deprecated per-message events (gen_ai.user.message, gen_ai.choice, …),
    # two LLM calls in one trace; the unrelated app log record is ignored.
    tutor = by_id["7c1a0f1e2d3b4c5d6e7f8091a2b3c4d5"]
    assert _roles(tutor) == ["system", "user", "assistant", "tool", "assistant"]
    call = tutor.steps[2]
    assert (call.tool_name, call.tool_input, call.tool_call_id) == (
        "multiply",
        {"a": 6, "b": 7},
        "call_mul",
    )
    assert (tutor.steps[3].tool_name, tutor.steps[3].content) == ("multiply", "42")
    assert tutor.steps[4].content == "6 times 7 is 42."

    # gen_ai.client.inference.operation.details carries the message attributes.
    details = by_id["9e8d7c6b5a4f3e2d1c0b9a8776655443"]
    assert [(s.role, s.content) for s in details.steps] == [
        ("user", "Name a prime."),
        ("assistant", "7"),
    ]


def test_langfuse_generations_in_start_order():
    _, traces = parse_traces(_read("langfuse.json"), "langfuse")
    trace = traces[0]
    assert trace.external_id == "lf-trace-1"
    assert trace.title == "support-chat"
    assert _roles(trace) == ["system", "user", "assistant", "tool", "assistant"]
    assert trace.steps[2].tool_input == {"id": "PKG9"}
    assert trace.steps[3].tool_name == "track"
    assert trace.steps[4].content == "It arrives Friday."


def test_langsmith_groups_runs_by_trace_id():
    _, traces = parse_traces(_read("langsmith.jsonl"), "langsmith")
    by_id = {t.external_id: t for t in traces}
    calc = by_id["1f0a0000-0000-0000-0000-000000000001"]
    assert _roles(calc) == ["system", "user", "assistant", "tool", "assistant"]
    call = calc.steps[2]
    assert (call.tool_name, call.tool_input, call.tool_call_id) == (
        "multiply",
        {"a": 12, "b": 7},
        "call_m1",
    )
    assert calc.steps[3].tool_name == "multiply"
    assert calc.steps[4].content == "12*7 = 84"

    # OpenAI-style runs (wrap_openai) in the same export.
    assert [(s.role, s.content) for s in by_id["trace-2"].steps] == [
        ("user", "ping"),
        ("assistant", "pong"),
    ]

    # Documented `{"messages": [...]}` output with reasoning and tool_call blocks.
    research = by_id["trace-3"]
    assert _roles(research) == ["user", "assistant", "assistant"]
    assert research.steps[1].metadata == {"thinking": True}
    assert (research.steps[2].tool_name, research.steps[2].tool_input) == ("search", {"q": "GEPA"})

    # Documented `["assistant", text]` output.
    assert research.steps[0].content == "Find papers on GEPA."
    assert by_id["trace-4"].steps[1].content == "Sure, what time?"


def test_claude_code_keeps_only_the_conversation():
    _, traces = parse_traces(_read("claude_code.jsonl"), "claude_code")
    assert len(traces) == 1
    trace = traces[0]
    assert trace.external_id == "3f1c2a8e-0000-4000-8000-00000000abcd"
    assert trace.title == "Fix add() in calc.py"
    assert trace.metadata == {"cwd": "/work/demo", "git_branch": "main"}
    # Meta, sidechain, API-error and bookkeeping lines and the empty (redacted)
    # thinking block are all gone.
    assert _roles(trace) == [
        "user",
        "assistant",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
    contents = " ".join(s.content for s in trace.steps)
    assert "Caveat" not in contents
    assert "subagent prompt" not in contents
    assert "API Error" not in contents

    read_call, read_result = trace.steps[2], trace.steps[3]
    assert read_call.tool_name == "Read"
    assert read_call.tool_input == {"file_path": "/work/demo/calc.py"}
    assert (read_result.tool_name, read_result.tool_call_id) == ("Read", "toolu_r1")
    assert trace.steps[5].metadata == {"is_error": True, "timestamp": "2026-09-03T12:00:00+00:00"}


def test_codex_response_items():
    _, traces = parse_traces(_read("codex.jsonl"), "codex")
    trace = traces[0]
    assert trace.external_id == "01a0ffff-0000-7000-8000-000000000001"
    assert trace.metadata == {"cwd": "/work/app", "cli_version": "0.150.0"}
    # developer → system; the empty reasoning item is dropped; event_msg and
    # turn_context lines are ignored.
    assert _roles(trace) == [
        "system",
        "user",
        "assistant",  # reasoning summary
        "assistant",  # function_call
        "tool",
        "assistant",  # custom_tool_call
        "tool",
        "assistant",
    ]
    assert trace.steps[2].metadata == {"thinking": True, "timestamp": "2026-09-04T08:00:00+00:00"}
    shell = trace.steps[3]
    assert shell.tool_input == {"command": ["wc", "-l", "main.py"]}
    assert (trace.steps[4].tool_name, trace.steps[4].content) == ("shell", "42 main.py")
    # Freeform tool input is raw text, wrapped so tool_input stays an object.
    assert trace.steps[5].tool_input == {"input": "*** Begin Patch\n*** End Patch"}
    assert (trace.steps[6].tool_name, trace.steps[6].content) == ("apply_patch", "Done")


# --- failures ---------------------------------------------------------------


def test_auto_garbage_lists_formats_tried():
    with pytest.raises(TraceFormatError) as excinfo:
        parse_traces("this is not a trace", "auto")
    message = str(excinfo.value)
    for name, _, _, _ in FORMATS:
        assert name in message


def test_unknown_format_name():
    with pytest.raises(TraceFormatError, match="unknown format 'csv'"):
        parse_traces(_read("stash.jsonl"), "csv")


def test_explicit_format_on_wrong_payload_fails_loud():
    with pytest.raises(TraceFormatError, match="could not parse as otel"):
        parse_traces(_read("stash.jsonl"), "otel")


def test_invalid_json_line_names_the_line():
    with pytest.raises(TraceFormatError, match="line 2"):
        parse_traces('{"steps": []}\n{not json\n', "stash")


def test_empty_trace_is_rejected():
    with pytest.raises(TraceFormatError, match="has no steps"):
        parse_traces('{"id": "t1", "steps": []}', "stash")


def test_empty_input_is_rejected():
    with pytest.raises(TraceFormatError):
        parse_traces("   \n", "stash")


def test_invalid_role_is_rejected():
    with pytest.raises(TraceFormatError, match="invalid role 'bot'"):
        parse_traces('{"steps": [{"role": "bot", "content": "hi"}]}', "stash")


def test_non_string_content_is_rejected():
    with pytest.raises(TraceFormatError, match="content must be a string"):
        parse_traces('{"steps": [{"role": "user", "content": 5}]}', "stash")


def test_codex_session_without_conversation_is_rejected():
    empty_rollout = '{"type": "session_meta", "payload": {"id": "s1", "cwd": "/w"}}\n'
    with pytest.raises(TraceFormatError, match=r"trace 0 \(s1\) has no steps"):
        parse_traces(empty_rollout, "auto")


@pytest.mark.parametrize("name", ["claude_code.jsonl", "codex.jsonl"])
def test_session_import_keeps_recorded_message_times(name):
    _, traces = parse_traces(_read(name), "auto")
    assert all("timestamp" in step.metadata for step in traces[0].steps)


def test_message_timestamp_is_not_replaced_by_import_time():
    import json

    _, traces = parse_traces(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "Refund?", "timestamp": "2026-09-29T12:00:00Z"},
                    {"role": "assistant", "content": "Done"},
                ]
            }
        ),
        "openai_chat",
    )
    assert traces[0].steps[0].metadata["timestamp"] == "2026-09-29T12:00:00+00:00"
    assert "timestamp" not in traces[0].steps[1].metadata


@pytest.mark.parametrize("timestamp", ["yesterday", "2026-09-29T12:00:00"])
def test_invalid_message_timestamp_is_rejected(timestamp):
    import json

    data = json.dumps({"messages": [{"role": "user", "content": "hi", "timestamp": timestamp}]})
    with pytest.raises(TraceFormatError, match="timestamp"):
        parse_traces(data, "openai_chat")


def test_otel_preserves_parallel_spans_and_their_parent_relationships():
    import json

    payload = json.loads(_read("otel.json"))
    raw = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    raw.extend(
        [
            {
                "traceId": raw[0]["traceId"],
                "spanId": "research",
                "parentSpanId": "a1",
                "name": "Research agent",
                "startTimeUnixNano": "1200",
                "endTimeUnixNano": "1900",
            },
            {
                "traceId": raw[0]["traceId"],
                "spanId": "verify",
                "parentSpanId": "a1",
                "name": "Verify agent",
                "startTimeUnixNano": "1300",
                "endTimeUnixNano": "1800",
            },
        ]
    )
    _, traces = parse_traces(json.dumps(payload), "otel")
    spans = {span.id: span for span in traces[0].spans}
    assert spans["research"].parent_id == spans["verify"].parent_id == "a1"
    assert (
        int(spans["research"].start_ns)
        < int(spans["verify"].start_ns)
        < int(spans["research"].end_ns)
    )
    assert any(span.step_indices for span in spans.values())
    assert len(traces[0].steps) == len(parse_traces(_read("otel.json"), "otel")[1][0].steps)


@pytest.mark.parametrize("invalid", ["cycle", "reversed", "missing_step"])
def test_invalid_span_structure_fails_import(invalid):
    import json

    spans = [
        dict(
            id="agent",
            parent_id=None,
            name="Agent",
            kind="AGENT",
            start_ns="1",
            end_ns="9",
            input=None,
            output=None,
            step_indices=[0],
        )
    ]
    if invalid == "cycle":
        spans[0]["parent_id"] = "child"
        spans.append({**spans[0], "id": "child", "parent_id": "agent"})
    elif invalid == "reversed":
        spans[0]["end_ns"] = "0"
    else:
        spans[0]["step_indices"] = [99]
    data = json.dumps({"steps": [{"role": "user", "content": "hi"}], "spans": spans})
    with pytest.raises(TraceFormatError):
        parse_traces(data, "stash")
