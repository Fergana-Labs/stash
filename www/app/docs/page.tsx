import type { Metadata } from "next";
import Link from "next/link";

import { Callout, Code, CodeBlock, H2, H3, P, Title } from "./components";
import { NextPage, Pipeline } from "./parts";

export const metadata: Metadata = {
  title: "Stash Docs",
  description:
    "Annotate agent traces with + / − comments, train a reward model from them, and use it to post-train or to write a skill for your agent with GEPA.",
  alternates: { canonical: "/docs" },
};

const AUTO_UPLOAD = `import json, os, requests

STASH_URL = os.environ["STASH_URL"]
KEY = os.environ["STASH_API_KEY"]

# At the end of each agent run:
trace = json.dumps({"messages": messages})
requests.post(
    f"{STASH_URL}/api/v1/rm/traces/import",
    headers={"Authorization": f"Bearer {KEY}"},
    json={"format": "openai_chat", "data": trace},
).raise_for_status()`;

// A real skill from the demo above, shortened.
const SKILL_EXAMPLE = `---
name: refund-requests
description: Use when a customer asks for a refund
  or reports a damaged order.
---

## Required steps (always, in order)

1. **Look up the order before responding.**
   Never promise a refund based only on the
   customer's claim.
2. **Check the refund policy before committing.**
   Don't imply a refund is approved until then.
3. **Explain next steps**, with a realistic timeline.`;

const API_STEPS = `export STASH_URL=https://api.joinstash.ai
export STASH_API_KEY=<your key>
AUTH="Authorization: Bearer $STASH_API_KEY"
JSON="Content-Type: application/json"

# 1. Upload
jq -Rs '{format: "auto", data: .}' traces.jsonl \\
  | curl -s "$STASH_URL/api/v1/rm/traces/import" \\
      -H "$AUTH" -H "$JSON" --data @-

# 3a. Train a reward model, then download its weights
curl -s "$STASH_URL/api/v1/rm/reward-models" \\
  -H "$AUTH" -H "$JSON" \\
  -d '{"name": "refunds", "compute": "local"}'
curl -s "$STASH_URL/api/v1/rm/reward-models/<id>/weights" \\
  -H "$AUTH" -OJ

# 3b. Create a skill, then download it
curl -s "$STASH_URL/api/v1/rm/gepa-runs" \\
  -H "$AUTH" -H "$JSON" -d '{
    "reward_model_id": "<id>",
    "skill_name": "refund-requests",
    "skill_description": "Use for refund requests.",
    "task_model": "anthropic/claude-haiku-4-5",
    "reflection_model": "anthropic/claude-sonnet-5"
  }'
curl -s "$STASH_URL/api/v1/rm/gepa-runs/<id>/skill" \\
  -H "$AUTH" -o SKILL.md`;

export default function RewardModelsOverviewPage() {
  return (
    <>
      <Title>Stash</Title>
      <P>
        Stash makes it easy to annotate traces so that you can emphasize what you wish the agent would
        have done better. Once you submit your annotations, Stash converts that into an easy-to-use reward
        model that you can use to either post-train or prompt-optimize with GEPA.
      </P>
      <Pipeline />

      <H2>1. Upload your traces</H2>
      <P>
        Paste or upload a file on the Traces page. Stash reads OpenAI, Anthropic, OpenTelemetry,
        Langfuse, LangSmith, Claude Code, and Codex logs as they are; see{" "}
        <Link href="/docs/trace-format" className="text-brand hover:underline">Trace format</Link>.
      </P>
      <P>To upload automatically, have your agent send each trace when a run ends:</P>
      <CodeBlock>{AUTO_UPLOAD}</CodeBlock>

      <H2>2. Annotate them</H2>
      <P>
        Open a trace and mark it, or any step in it, + or −. To say what went wrong, highlight the text
        and leave a comment. The + and − marks train the reward model. The comments tell GEPA what to fix.
      </P>
      <Callout>
        Training needs at least two + / − pairs, for example two traces marked + and one marked −.
        See <Link href="/docs/annotations" className="text-brand hover:underline">Annotations</Link>.
      </Callout>

      <H2>3. Press a button</H2>
      <H3>Train reward model</H3>
      <P>
        On the Reward models tab. Stash trains a reward model on your + and − marks and scores every
        trace, including the ones nobody annotated. Press <strong>Download weights</strong> to take the
        model and use it as the reward function when you post-train.
      </P>
      <H3>Create skill</H3>
      <P>
        On the Skills tab. Name the skill and say when your agent should use it. GEPA writes the{" "}
        <Code>SKILL.md</Code> from your comments and keeps the version your reward model scores highest.
        Your agent loads it next to its system prompt, which Stash leaves alone. This one came out of
        the demo above:
      </P>
      <CodeBlock>{SKILL_EXAMPLE}</CodeBlock>

      <H2>The same steps over the API</H2>
      <P>
        Create an API key at{" "}
        <Link href="https://app.joinstash.ai/developer/keys" className="text-brand hover:underline">app.joinstash.ai/developer/keys</Link>.
        Step 2, annotating, happens in the app. Full reference:{" "}
        <Link href="/docs/api" className="text-brand hover:underline">API</Link>.
      </P>
      <CodeBlock>{API_STEPS}</CodeBlock>
      <P>
        Running your own Stash? Point <Code>STASH_URL</Code> at your backend; see{" "}
        <Link href="/docs/training#self-hosting-the-worker" className="text-brand hover:underline">Self-hosting the worker</Link>.
      </P>

      <NextPage href="/docs/trace-format" label="Trace format" />
    </>
  );
}
