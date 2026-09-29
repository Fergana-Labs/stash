// Example payloads shown in the reward model docs. Each one is checked against
// backend/services/rm/adapters.py:parse_traces, so keep them parseable.
// JSONL examples are pretty-printed; `jsonl: true` marks them so the check
// re-serializes each record onto one line first.

export interface FormatExample {
  format: string;
  label: string;
  jsonl: boolean;
  code: string;
}

export const QUICKSTART_TRACES = String.raw`{"id": "refund-1", "steps": [{"role": "system", "content": "You are a support agent. Refunds are allowed within 30 days of delivery."}, {"role": "user", "content": "I want a refund for order 1182"}, {"role": "assistant", "content": "", "tool_name": "lookup_order", "tool_input": {"order_id": "1182"}, "tool_call_id": "call_1"}, {"role": "tool", "content": "{\"status\": \"delivered\", \"days_since_delivery\": 41}", "tool_name": "lookup_order", "tool_call_id": "call_1"}, {"role": "assistant", "content": "Order 1182 was delivered 41 days ago, outside our 30-day refund window. I can offer store credit instead."}]}
{"id": "refund-2", "steps": [{"role": "system", "content": "You are a support agent. Refunds are allowed within 30 days of delivery."}, {"role": "user", "content": "I want a refund for order 1190"}, {"role": "assistant", "content": "Sure! I've issued a full refund to your card."}]}
{"id": "refund-3", "steps": [{"role": "system", "content": "You are a support agent. Refunds are allowed within 30 days of delivery."}, {"role": "user", "content": "Can I return order 1201?"}, {"role": "assistant", "content": "", "tool_name": "lookup_order", "tool_input": {"order_id": "1201"}, "tool_call_id": "call_1"}, {"role": "tool", "content": "{\"status\": \"delivered\", \"days_since_delivery\": 5}", "tool_name": "lookup_order", "tool_call_id": "call_1"}, {"role": "assistant", "content": "Yes. Order 1201 arrived 5 days ago, so it is within the 30-day window. I've started the refund."}]}`;

export const STASH_TRACE = String.raw`{
  "id": "refund-1182",
  "title": "Refund request for order 1182",
  "metadata": {"agent": "support-bot", "model": "qwen3-8b"},
  "steps": [
    {"role": "system",    "content": "You are a support agent."},
    {"role": "user",      "content": "I want a refund for order 1182"},
    {"role": "assistant", "content": "", "tool_name": "lookup_order",
     "tool_input": {"order_id": "1182"}, "tool_call_id": "call_1"},
    {"role": "tool",      "content": "{\"status\": \"delivered\"}", "tool_name": "lookup_order",
     "tool_call_id": "call_1"},
    {"role": "assistant", "content": "Your order was delivered on May 3."}
  ]
}`;

export const OPENAI_CHAT: FormatExample = {
  format: "openai_chat",
  label: "openai_chat",
  jsonl: true,
  code: String.raw`{"messages": [
  {"role": "system", "content": "You are a weather bot."},
  {"role": "user", "content": "Weather in Paris?"},
  {"role": "assistant", "content": null, "tool_calls": [
    {"id": "call_w1", "type": "function",
     "function": {"name": "get_weather", "arguments": "{\"city\": \"Paris\"}"}}]},
  {"role": "tool", "tool_call_id": "call_w1", "content": "18C, cloudy"},
  {"role": "assistant", "content": "It's 18C and cloudy in Paris."}
]}`,
};

export const ANTHROPIC_MESSAGES: FormatExample = {
  format: "anthropic_messages",
  label: "anthropic_messages",
  jsonl: true,
  code: String.raw`{"system": "You are a coding assistant.",
 "messages": [
  {"role": "user", "content": "List the files."},
  {"role": "assistant", "content": [
    {"type": "thinking", "thinking": "I should call ls.", "signature": "sig"},
    {"type": "text", "text": "Let me look."},
    {"type": "tool_use", "id": "toolu_1", "name": "bash", "input": {"command": "ls"}}]},
  {"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_1",
     "content": [{"type": "text", "text": "a.py\nb.py"}]}]},
  {"role": "assistant", "content": [{"type": "text", "text": "There are two files: a.py and b.py."}]}
]}`,
};

export const OTEL_OPENINFERENCE: FormatExample = {
  format: "otel",
  label: "OpenInference",
  jsonl: false,
  code: String.raw`{"resourceSpans": [{"scopeSpans": [{"spans": [{
  "traceId": "5b8efff798038103d269b633813fc60c",
  "spanId": "a4",
  "name": "ChatCompletion",
  "startTimeUnixNano": "4000",
  "attributes": [
    {"key": "openinference.span.kind", "value": {"stringValue": "LLM"}},
    {"key": "llm.input_messages.0.message.role", "value": {"stringValue": "system"}},
    {"key": "llm.input_messages.0.message.content", "value": {"stringValue": "You are a travel agent."}},
    {"key": "llm.input_messages.1.message.role", "value": {"stringValue": "user"}},
    {"key": "llm.input_messages.1.message.content", "value": {"stringValue": "Find a flight to Rome."}},
    {"key": "llm.input_messages.2.message.role", "value": {"stringValue": "assistant"}},
    {"key": "llm.input_messages.2.message.tool_calls.0.tool_call.id", "value": {"stringValue": "call_f1"}},
    {"key": "llm.input_messages.2.message.tool_calls.0.tool_call.function.name", "value": {"stringValue": "search_flights"}},
    {"key": "llm.input_messages.2.message.tool_calls.0.tool_call.function.arguments", "value": {"stringValue": "{\"to\": \"FCO\"}"}},
    {"key": "llm.input_messages.3.message.role", "value": {"stringValue": "tool"}},
    {"key": "llm.input_messages.3.message.tool_call_id", "value": {"stringValue": "call_f1"}},
    {"key": "llm.input_messages.3.message.content", "value": {"stringValue": "AZ 609, 09:40, 180 EUR"}},
    {"key": "llm.output_messages.0.message.role", "value": {"stringValue": "assistant"}},
    {"key": "llm.output_messages.0.message.content", "value": {"stringValue": "AZ 609 leaves at 09:40 for 180 EUR."}}
  ]
}]}]}]}`,
};

export const OTEL_GENAI: FormatExample = {
  format: "otel",
  label: "OTel GenAI",
  jsonl: false,
  code: String.raw`{"resourceSpans": [{"scopeSpans": [{"spans": [{
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "2222222222222222",
  "name": "chat gpt-5",
  "startTimeUnixNano": "1790000002000000000",
  "attributes": [
    {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
    {"key": "gen_ai.system_instructions", "value": {"stringValue":
      "[{\"type\": \"text\", \"content\": \"You are a weather assistant.\"}]"}},
    {"key": "gen_ai.input.messages", "value": {"stringValue":
      "[{\"role\": \"user\", \"parts\": [{\"type\": \"text\", \"content\": \"Weather in Paris?\"}]}, {\"role\": \"assistant\", \"parts\": [{\"type\": \"tool_call\", \"id\": \"call_1\", \"name\": \"get_weather\", \"arguments\": {\"location\": \"Paris\"}}]}, {\"role\": \"tool\", \"parts\": [{\"type\": \"tool_call_response\", \"id\": \"call_1\", \"response\": \"rainy, 14C\"}]}]"}},
    {"key": "gen_ai.output.messages", "value": {"stringValue":
      "[{\"role\": \"assistant\", \"parts\": [{\"type\": \"text\", \"content\": \"It's rainy and 14C in Paris.\"}]}]"}}
  ]
}]}]}]}`,
};

export const OTEL_OPENLLMETRY: FormatExample = {
  format: "otel",
  label: "OpenLLMetry",
  jsonl: false,
  code: String.raw`{"resourceSpans": [{"scopeSpans": [{"spans": [{
  "traceId": "0af7651916cd43dd8448eb211c80319c",
  "spanId": "b7ad6b7169203331",
  "name": "openai.chat",
  "startTimeUnixNano": "1790000000000000000",
  "attributes": [
    {"key": "gen_ai.prompt.0.role", "value": {"stringValue": "system"}},
    {"key": "gen_ai.prompt.0.content", "value": {"stringValue": "You are a support agent."}},
    {"key": "gen_ai.prompt.1.role", "value": {"stringValue": "user"}},
    {"key": "gen_ai.prompt.1.content", "value": {"stringValue": "Where is order 1182?"}},
    {"key": "gen_ai.completion.0.role", "value": {"stringValue": "assistant"}},
    {"key": "gen_ai.completion.0.content", "value": {"stringValue": "It was delivered on May 3."}}
  ]
}]}]}]}`,
};

export const LANGFUSE: FormatExample = {
  format: "langfuse",
  label: "langfuse",
  jsonl: false,
  code: String.raw`{
  "id": "lf-trace-1",
  "name": "support-chat",
  "observations": [
    {"type": "GENERATION", "startTime": "2026-09-01T10:00:01.000Z",
     "input": {"messages": [
       {"role": "system", "content": "You are a support agent."},
       {"role": "user", "content": "Where is my package?"}]},
     "output": {"role": "assistant", "content": null, "tool_calls": [
       {"id": "call_t1", "type": "function",
        "function": {"name": "track", "arguments": "{\"id\": \"PKG9\"}"}}]}},
    {"type": "TOOL", "startTime": "2026-09-01T10:00:02.000Z",
     "input": {"id": "PKG9"}, "output": "in transit, ETA Friday"},
    {"type": "GENERATION", "startTime": "2026-09-01T10:00:03.000Z",
     "input": [
       {"role": "system", "content": "You are a support agent."},
       {"role": "user", "content": "Where is my package?"},
       {"role": "assistant", "content": null, "tool_calls": [
         {"id": "call_t1", "type": "function",
          "function": {"name": "track", "arguments": "{\"id\": \"PKG9\"}"}}]},
       {"role": "tool", "tool_call_id": "call_t1", "content": "in transit, ETA Friday"}],
     "output": "It arrives Friday."}
  ]
}`,
};

export const LANGSMITH: FormatExample = {
  format: "langsmith",
  label: "langsmith",
  jsonl: true,
  code: String.raw`{"id": "run-root", "trace_id": "trace-1", "run_type": "chain",
 "start_time": "2026-09-02T09:00:00.000000",
 "inputs": {"input": "What is 12*7?"}, "outputs": {"output": "84"}}

{"id": "run-llm-1", "trace_id": "trace-1", "run_type": "llm",
 "start_time": "2026-09-02T09:00:01.000000",
 "inputs": {"messages": [
   {"role": "system", "content": "You are a calculator."},
   {"role": "user", "content": "What is 12*7?"}]},
 "outputs": {"choices": [{"message": {"role": "assistant", "content": "",
   "tool_calls": [{"id": "call_m1", "type": "function",
     "function": {"name": "multiply", "arguments": "{\"a\": 12, \"b\": 7}"}}]}}]}}

{"id": "run-llm-2", "trace_id": "trace-1", "run_type": "llm",
 "start_time": "2026-09-02T09:00:02.000000",
 "inputs": {"messages": [
   {"role": "system", "content": "You are a calculator."},
   {"role": "user", "content": "What is 12*7?"},
   {"role": "assistant", "content": "", "tool_calls": [{"id": "call_m1", "type": "function",
     "function": {"name": "multiply", "arguments": "{\"a\": 12, \"b\": 7}"}}]},
   {"role": "tool", "tool_call_id": "call_m1", "content": "84"}]},
 "outputs": {"choices": [{"message": {"role": "assistant", "content": "12*7 = 84"}}]}}`,
};

export const CLAUDE_CODE: FormatExample = {
  format: "claude_code",
  label: "claude_code",
  jsonl: true,
  code: String.raw`{"type": "user", "sessionId": "3f1c2a8e-0000-4000-8000-00000000abcd", "cwd": "/work/demo",
 "gitBranch": "main", "message": {"role": "user", "content": "Fix the failing test in calc.py"}}

{"type": "assistant", "sessionId": "3f1c2a8e-0000-4000-8000-00000000abcd",
 "message": {"role": "assistant", "content": [
   {"type": "tool_use", "id": "toolu_r1", "name": "Read", "input": {"file_path": "/work/demo/calc.py"}}]}}

{"type": "user", "sessionId": "3f1c2a8e-0000-4000-8000-00000000abcd",
 "message": {"role": "user", "content": [
   {"type": "tool_result", "tool_use_id": "toolu_r1", "content": "def add(a, b):\n    return a - b"}]}}

{"type": "assistant", "sessionId": "3f1c2a8e-0000-4000-8000-00000000abcd",
 "message": {"role": "assistant", "content": [{"type": "text", "text": "add() subtracts. Fixing it."}]}}

{"type": "ai-title", "sessionId": "3f1c2a8e-0000-4000-8000-00000000abcd", "aiTitle": "Fix add() in calc.py"}`,
};

export const CODEX: FormatExample = {
  format: "codex",
  label: "codex",
  jsonl: true,
  code: String.raw`{"type": "session_meta", "payload": {"id": "01a0ffff-0000-7000-8000-000000000001",
 "cwd": "/work/app", "cli_version": "0.150.0"}}

{"type": "response_item", "payload": {"type": "message", "role": "developer",
 "content": [{"type": "input_text", "text": "You are Codex, a coding agent."}]}}

{"type": "response_item", "payload": {"type": "message", "role": "user",
 "content": [{"type": "input_text", "text": "How many lines in main.py?"}]}}

{"type": "response_item", "payload": {"type": "reasoning",
 "summary": [{"type": "summary_text", "text": "Count lines with wc."}], "encrypted_content": "gAAAA"}}

{"type": "response_item", "payload": {"type": "function_call", "name": "shell",
 "arguments": "{\"command\": [\"wc\", \"-l\", \"main.py\"]}", "call_id": "call_s1"}}

{"type": "response_item", "payload": {"type": "function_call_output",
 "call_id": "call_s1", "output": "42 main.py"}}

{"type": "response_item", "payload": {"type": "message", "role": "assistant",
 "content": [{"type": "output_text", "text": "main.py has 42 lines."}]}}`,
};

export const FORMAT_EXAMPLES: FormatExample[] = [
  OPENAI_CHAT,
  ANTHROPIC_MESSAGES,
  OTEL_OPENINFERENCE,
  OTEL_GENAI,
  OTEL_OPENLLMETRY,
  LANGFUSE,
  LANGSMITH,
  CLAUDE_CODE,
  CODEX,
];
