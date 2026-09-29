import type { Metadata } from "next";

import { Code, CodeBlock, CodeTabs, H2, H3, P, ParamTable, Title, Subtitle } from "../components";
import {
  ANTHROPIC_MESSAGES,
  CLAUDE_CODE,
  CODEX,
  LANGFUSE,
  LANGSMITH,
  OPENAI_CHAT,
  OTEL_GENAI,
  OTEL_OPENINFERENCE,
  OTEL_OPENLLMETRY,
  STASH_TRACE,
} from "../examples";
import { NextPage, Table } from "../parts";

export const metadata: Metadata = {
  title: "Trace Format · Stash Docs",
  description:
    "The Stash Trace Format spec and the eight input formats Stash imports: OpenAI, Anthropic, OpenTelemetry, Langfuse, LangSmith, Claude Code, Codex, and Stash JSONL.",
  alternates: { canonical: "/docs/trace-format" },
};

export default function TraceFormatPage() {
  return (
    <>
      <Title>Trace format</Title>
      <Subtitle>
        One JSONL shape for import, export, and every adapter. Bring any of eight formats; Stash converts them to this.
      </Subtitle>

      <H2>Stash Trace Format</H2>
      <P>
        One trace per line. A trace is an ordered list of steps. The same shape is what{" "}
        <Code>GET /api/v1/rm/export/traces</Code> returns, so an export re-imports cleanly with{" "}
        <Code>format: &quot;stash&quot;</Code>. Pretty-printed here; in a file, each trace is one line.
      </P>
      <CodeBlock lang="json">{STASH_TRACE}</CodeBlock>

      <H3>Trace fields</H3>
      <ParamTable
        params={[
          { name: "steps", type: "array", desc: "The conversation, in order. At least one step, and at least one that isn't a system step.", required: true },
          {
            name: "id",
            type: "string",
            desc: "Your external id. Re-importing a trace with the same id replaces its steps, and the annotations on the old steps are deleted with them.",
          },
          {
            name: "title",
            type: "string",
            desc: "Display title. Defaults to the first 80 characters of the first user step. A trace with no title and no user step fails import.",
          },
          { name: "metadata", type: "object", desc: "Free-form key/value data about the trace, such as agent name or model." },
        ]}
      />

      <H3>Step fields</H3>
      <ParamTable
        params={[
          { name: "role", type: "string", desc: "One of system, user, assistant, tool.", required: true },
          {
            name: "content",
            type: "string",
            desc: "Always a string. Structured tool output is serialized JSON. An assistant step that only calls a tool has empty content.",
            required: true,
          },
          { name: "tool_name", type: "string", desc: "On an assistant step: the tool it calls. On a tool step: the tool that produced the result." },
          { name: "tool_input", type: "object", desc: "The arguments of the tool call. Must be an object." },
          { name: "tool_call_id", type: "string", desc: "Links a tool step to the assistant step that called it." },
          { name: "metadata", type: "object", desc: 'Free-form, per step. Adapters set {"thinking": true} on model reasoning and {"is_error": true} on failed tool results.' },
        ]}
      />
      <P>
        Every adapter below writes a tool call and its result as that pair of steps, and fills in the
        tool step&apos;s <Code>tool_name</Code> from the matching call.
      </P>
      <P>
        Adapters put an assistant message&apos;s text and each of its tool calls in separate steps. In the
        Stash format you can also put both on one assistant step; the reward model then sees the text
        line followed by the tool call line.
      </P>

      <H3>System steps</H3>
      <P>
        System steps are stored and shown, but the reward model never sees them. GEPA puts the skill it
        writes into the system message, so a reward model that read the system message could be
        satisfied by the skill&apos;s text instead of by what the agent does. You can comment on a system step, but not rate it, and a trace with
        only system steps fails import.
      </P>

      <H2>Supported input formats</H2>
      <P>
        Pass <Code>format</Code> on import as one of these names, or <Code>auto</Code>. One import
        call takes one payload: the contents of one file.
      </P>
      <Table
        head={["format", "input", "one trace per", "trace id"]}
        rows={[
          ["stash", "Stash Trace Format JSONL", "line", <Code key="c">id</Code>],
          ["openai_chat", <>JSONL of <Code>{`{"messages": [...]}`}</Code> (fine-tuning format), or a JSON array of messages</>, "line", "none"],
          ["anthropic_messages", <>JSONL of <Code>{`{"system": ..., "messages": [...]}`}</Code></>, "line", "none"],
          ["otel", <>OTLP/JSON with <Code>resourceSpans</Code> and/or <Code>resourceLogs</Code>: one export request, or Collector file-exporter JSONL</>, <Code key="c">traceId</Code>, <Code key="c">traceId</Code>],
          ["langfuse", <>The <Code>GET /api/public/traces/&#123;traceId&#125;</Code> response, one object or a JSON array</>, "trace", <Code key="c">id</Code>],
          ["langsmith", "LangSmith run export JSONL", <Code key="c">trace_id</Code>, <Code key="c">trace_id</Code>],
          ["claude_code", <>Claude Code session transcript (<Code>~/.claude/projects/**/*.jsonl</Code>)</>, "file", <Code key="c">sessionId</Code>],
          ["codex", <>Codex CLI rollout (<Code>~/.codex/sessions/**/rollout-*.jsonl</Code>)</>, "file", "session id"],
        ]}
      />
      <P>
        The trace id column is what becomes the trace&apos;s <Code>id</Code>. For every format except{" "}
        <Code>openai_chat</Code> and <Code>anthropic_messages</Code>, re-importing the same file replaces
        the traces it created instead of adding copies.
      </P>

      <H3>Auto-detection</H3>
      <P>
        With <Code>format: &quot;auto&quot;</Code>, Stash checks the payload&apos;s shape against each format
        in the order of the table above and uses the first match. The response&apos;s{" "}
        <Code>format</Code> field tells you which one it picked. When nothing matches, the import fails
        with a <Code>422</Code>:
      </P>
      <CodeBlock lang="text">{`could not detect the trace format; tried: stash, openai_chat, anthropic_messages, otel, langfuse, langsmith, claude_code, codex`}</CodeBlock>
      <P>
        The whole payload is parsed and checked before anything is stored, so a failed import stores
        nothing. Parse errors name the format, for example <Code>could not parse as otel: …</Code>. Pass an explicit format when you want a payload to
        fail rather than be read as something else.
      </P>

      <H3>Agent loops with many LLM calls</H3>
      <P>
        <Code>otel</Code>, <Code>langfuse</Code>, and <Code>langsmith</Code> record one entry per LLM call,
        and each call re-sends the conversation so far. Stash sorts a trace&apos;s calls by start time and
        joins them: when the steps collected so far are a prefix of the next call&apos;s messages, only
        the new messages are appended. A call that doesn&apos;t continue the conversation is appended
        whole. Model reasoning is left out of that comparison, since most APIs don&apos;t re-send it.
      </P>
      <P>
        Only LLM calls are read. Tool spans, tool observations, and tool or chain runs are skipped,
        because every tool call and its result already appear in the next LLM call&apos;s messages.
      </P>

      <H2>Format examples</H2>
      <P>
        A minimal input for each format, and how it maps onto steps. Each example here imports as-is;
        JSONL examples are pretty-printed, so put each record on one line (<Code>jq -c .</Code> does
        this).
      </P>

      <H3>openai_chat</H3>
      <CodeBlock lang="json">{OPENAI_CHAT.code}</CodeBlock>
      <P>
        <Code>system</Code> and <Code>developer</Code> messages become system steps. Each entry in{" "}
        <Code>tool_calls</Code> becomes an assistant step with <Code>tool_name</Code> from{" "}
        <Code>function.name</Code>, <Code>tool_input</Code> parsed from <Code>function.arguments</Code>, and{" "}
        <Code>tool_call_id</Code> from <Code>id</Code>. Each <Code>role: &quot;tool&quot;</Code> message
        becomes a tool step. When content is a list of parts, each part becomes its own step. A bare
        JSON array of messages is read as one trace.
      </P>

      <H3>anthropic_messages</H3>
      <CodeBlock lang="json">{ANTHROPIC_MESSAGES.code}</CodeBlock>
      <P>
        <Code>system</Code> becomes the first step. Content blocks become steps in order:{" "}
        <Code>text</Code> keeps its role, <Code>tool_use</Code> becomes an assistant tool call step,{" "}
        <Code>tool_result</Code> becomes a tool step even though Anthropic sends it inside a user
        message, and <Code>thinking</Code> becomes an assistant step with{" "}
        <Code>{`{"thinking": true}`}</Code> in its metadata. Empty and redacted thinking is dropped. Other
        blocks, such as images, become a marker like <Code>[image]</Code>.
      </P>

      <H3>otel</H3>
      <P>Three conventions are read. Any of them can appear in the same export.</P>
      <CodeTabs
        tabs={[OTEL_OPENINFERENCE, OTEL_GENAI, OTEL_OPENLLMETRY].map((example) => ({
          label: example.label,
          lang: "json",
          code: example.code,
        }))}
      />
      <Table
        head={["convention", "read from"]}
        rows={[
          [
            "OpenInference",
            <>
              <Code key="a">llm.input_messages.N.message.*</Code> and <Code key="b">llm.output_messages.N.message.*</Code>, including{" "}
              <Code key="c">message.tool_calls</Code> and <Code key="d">message.contents</Code>
            </>,
          ],
          [
            "OTel GenAI",
            <>
              <Code key="a">gen_ai.system_instructions</Code>, <Code key="b">gen_ai.input.messages</Code>, <Code key="c">gen_ai.output.messages</Code>{" "}
              on spans or on a <Code key="d">gen_ai.client.inference.operation.details</Code> log event, plus the deprecated per-message
              log events (<Code key="e">gen_ai.user.message</Code>, <Code key="f">gen_ai.choice</Code>, …)
            </>,
          ],
          ["OpenLLMetry", <><Code key="a">gen_ai.prompt.N.*</Code> and <Code key="b">gen_ai.completion.N.*</Code></>],
        ]}
      />
      <P>
        The GenAI message attributes may be structured OTLP values or JSON strings. Spans and log records are
        grouped by <Code>traceId</Code>, and each group&apos;s LLM calls are joined into one conversation
        as described <a href="#agent-loops-with-many-llm-calls" className="text-brand hover:underline">above</a>.
      </P>

      <H3>langfuse</H3>
      <CodeBlock lang="json">{LANGFUSE.code}</CodeBlock>
      <P>
        Send the body of Langfuse&apos;s <Code>GET /api/public/traces/&#123;traceId&#125;</Code>, or a JSON
        array of them. Each trace keeps its Langfuse <Code>id</Code> and uses its <Code>name</Code> as the
        title. Its <Code>GENERATION</Code> observations are read in <Code>startTime</Code> order: the input
        is a message list, bare or under <Code>messages</Code>, and the output is an assistant message or
        plain text. The <Code>TOOL</Code> observation above is skipped; its call and result are already
        in the second generation&apos;s input.
      </P>

      <H3>langsmith</H3>
      <CodeBlock lang="json">{LANGSMITH.code}</CodeBlock>
      <P>
        One run per line, grouped by <Code>trace_id</Code>. Only <Code>llm</Code> runs are read, in{" "}
        <Code>start_time</Code> order. Messages can be role/content objects, LangChain-serialized messages
        (<Code>{`{"lc": 1, "id": [..., "AIMessage"], "kwargs": {...}}`}</Code>), or{" "}
        <Code>{`{"type": "ai", ...}`}</Code> objects. Outputs can be LangChain <Code>generations</Code>,
        OpenAI <Code>choices</Code>, a <Code>messages</Code> list, or a single message.
      </P>

      <H3>claude_code</H3>
      <CodeBlock lang="json">{CLAUDE_CODE.code}</CodeBlock>
      <P>
        One session file is one trace, keyed by <Code>sessionId</Code> and titled with the last{" "}
        <Code>ai-title</Code> line. Only <Code>user</Code> and <Code>assistant</Code> lines are read, and
        lines marked <Code>isMeta</Code>, <Code>isSidechain</Code>, <Code>isCompactSummary</Code>, or{" "}
        <Code>isApiErrorMessage</Code> are skipped. Content blocks map the same way as{" "}
        <Code>anthropic_messages</Code>. <Code>cwd</Code> and <Code>gitBranch</Code> go into the
        trace&apos;s metadata. To import every session in a project, send one request per file:
      </P>
      <CodeBlock lang="bash">{`for f in ~/.claude/projects/-Users-me-myrepo/*.jsonl; do
  jq -Rs '{format: "claude_code", data: .}' "$f" \\
    | curl -s "$STASH_URL/api/v1/rm/traces/import" \\
        -H "Authorization: Bearer $STASH_API_KEY" \\
        -H "Content-Type: application/json" --data @-
done`}</CodeBlock>

      <H3>codex</H3>
      <CodeBlock lang="json">{CODEX.code}</CodeBlock>
      <P>
        One rollout file is one trace, keyed by the <Code>session_meta</Code> id. Only{" "}
        <Code>response_item</Code> lines are read. <Code>developer</Code> messages become system steps,{" "}
        <Code>function_call</Code> and <Code>custom_tool_call</Code> become assistant tool call steps, their
        outputs become tool steps joined on <Code>call_id</Code>, and a reasoning item&apos;s readable
        summary becomes a thinking step. <Code>cwd</Code> and <Code>cli_version</Code> go into the
        trace&apos;s metadata.
      </P>

      <NextPage href="/docs/annotations" label="Annotations" />
    </>
  );
}
