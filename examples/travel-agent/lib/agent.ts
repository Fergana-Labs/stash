import Anthropic from "@anthropic-ai/sdk";
import type { MessageParam, Tool, ToolResultBlockParam } from "@anthropic-ai/sdk/resources/messages";
import { runScript, type Turn } from "./stash";

const MODEL = "claude-sonnet-4-6";

// The model gets this many chances to read Stash before it has to answer with
// what it has. A travel question needs one or two.
const MAX_TURNS = 6;

// What comes back from a read goes into the model's context, so a `cat` of the
// whole wiki has to be bounded somewhere.
const MAX_TOOL_OUTPUT = 6000;

/** What the browser draws: assistant text, and each Stash read as it happens. */
export type AgentEvent =
  | { type: "text"; delta: string }
  | { type: "tool"; id: string; script: string }
  | { type: "tool_result"; id: string; ok: boolean; summary: string };

const SEARCH_STASH: Tool = {
  name: "search_stash",
  description: `Read Stash — everything you know about travel. One read-only shell command per call, run against this traveller's own view.

- /memory — the shared wiki: what travel agents have learned about the world across everyone you book for, rebuilt nightly. Start here.
- /files — this traveller's own notes.
- /sessions — your past conversations with this traveller.

Supported: ls, cat, find, grep, head, tail, wc, and pipes between them. Read-only — no writes, no redirects. Every call runs from the root, so use absolute paths (\`ls /memory\`, not \`cd /memory && ls\`).

grep supports -i, -r, -n and -A/-B/-C, but NOT -l; a recursive grep already prints matches as \`path:line\`. Exit code 1 from grep means no matches, which is a normal result, not an error.`,
  input_schema: {
    type: "object",
    properties: {
      script: {
        type: "string",
        description: 'One command, e.g. `ls /memory` or `grep -ri "visa" /memory`.',
      },
    },
    required: ["script"],
  },
};

const SYSTEM = `You are Atlas, a travel agent. The person you are talking to is
planning a trip of their own — talk to them the way a good agent talks to a
client they know.

Check Stash before you answer. Anything you think you know about visa
timelines, seasons, routings, or a destination has probably been sharpened by
what other travellers actually lived through, and that is in /memory — where
the published figure and the observed one can differ enormously. Start with
\`ls /memory\` and read the pages that bear on the question, then check /files
for what this traveller has told you before. Answer from what you read, not
from memory, and prefer what Stash says over your own prior belief when they
disagree.

Be concrete — name airlines, airports, visa timelines, neighbourhoods — and say
plainly when a plan is at risk. Two or three sentences unless they ask for a
full itinerary.

You do not know who else you book for and must never speculate about them.`;

let client: Anthropic | null = null;

function anthropic(): Anthropic {
  if (client) return client;
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY is not set — put it in .env.local");
  client = new Anthropic({ apiKey });
  return client;
}

/**
 * An Anthropic tool-use loop: the model asks to read Stash, we run the command
 * against that traveller's tenant view, hand back what it printed, and go round
 * again until it answers. `tenant` is the only isolation Stash needs — the
 * model never sees another traveller's view, whatever command it writes.
 *
 * Deliberately not the Claude Agent SDK: that runs the `claude` CLI as a
 * subprocess behind an MCP boundary, which is what backend/services/tool_loop.py
 * abandoned — see its docstring. This is the same native loop, in TypeScript.
 */
export async function* answer(tenant: string, history: Turn[]): AsyncGenerator<AgentEvent> {
  const messages: MessageParam[] = history.map((turn) => ({
    role: turn.role,
    content: turn.content,
  }));

  for (let turn = 0; turn < MAX_TURNS; turn++) {
    const stream = anthropic().messages.stream({
      model: MODEL,
      max_tokens: 1200,
      system: SYSTEM,
      tools: [SEARCH_STASH],
      messages,
    });

    for await (const event of stream) {
      if (event.type === "content_block_delta" && event.delta.type === "text_delta")
        yield { type: "text", delta: event.delta.text };
    }

    // Tool calls come off the finished message, where their input is already
    // parsed. Streaming partial tool JSON to the browser is the jank we avoid:
    // a call surfaces once, with real arguments.
    const said = await stream.finalMessage();
    messages.push({ role: "assistant", content: said.content });

    const calls = said.content.filter((block) => block.type === "tool_use");
    if (!calls.length) return;

    const results: ToolResultBlockParam[] = [];
    for (const call of calls) {
      const script = String((call.input as { script?: string }).script ?? "");
      yield { type: "tool", id: call.id, script };
      const run = await runScript(tenant, script);
      yield {
        type: "tool_result",
        id: call.id,
        ok: run.exitCode === 0,
        summary: summarize(run.stdout, run.stderr, run.exitCode),
      };
      results.push({
        type: "tool_result",
        tool_use_id: call.id,
        content: clip(run.stdout.trim() || run.stderr.trim()) || "(no output)",
        is_error: run.exitCode !== 0 && !run.stdout.trim(),
      });
    }
    messages.push({ role: "user", content: results });
  }
}

function summarize(stdout: string, stderr: string, exitCode: number): string {
  const lines = stdout.trim() ? stdout.trim().split("\n").length : 0;
  if (lines) return `${lines} line${lines === 1 ? "" : "s"}`;
  if (exitCode !== 0) return stderr.trim().split("\n")[0] || "no matches";
  return "empty";
}

function clip(text: string): string {
  if (text.length <= MAX_TOOL_OUTPUT) return text;
  return `${text.slice(0, MAX_TOOL_OUTPUT)}\n… truncated, ${text.length - MAX_TOOL_OUTPUT} more characters`;
}
