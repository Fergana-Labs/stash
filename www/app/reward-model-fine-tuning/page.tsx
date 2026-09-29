import type { Metadata } from "next";
import Link from "next/link";

import { Callout, Code, CodeBlock, H2, H3, P, Title, Subtitle } from "../docs/components";
import { QUICKSTART_TRACES } from "./examples";
import { NextPage, Pipeline, Table } from "./parts";

export const metadata: Metadata = {
  title: "Stash reward model fine-tuning",
  description:
    "Import agent traces, annotate them with + / − comments, train a Bradley–Terry reward model, and optimize system prompts with GEPA.",
  alternates: { canonical: "/reward-model-fine-tuning" },
};

const SAMPLE = `cat > traces.jsonl <<'EOF'
${QUICKSTART_TRACES}
EOF`;

export default function RewardModelsOverviewPage() {
  return (
    <>
      <Title>Stash reward model fine-tuning</Title>
      <Subtitle>
        Turn reviewed agent traces into a reward model, then use it to rewrite your agent&apos;s system prompt.
      </Subtitle>

      <P>
        You bring traces from whatever your agent already logs. Your team reviews them the way
        they&apos;d review a Google Doc: highlight a span, leave a comment, mark it + or −. Stash
        turns the ratings into preference pairs and trains a reward model on them, the same kind
        of model used in RLHF. The written comments go to GEPA, a prompt optimizer that reads them
        as feedback while it searches for a better system prompt, and uses your reward model to
        score each candidate.
      </P>

      <Pipeline />

      <H2>Who it&apos;s for</H2>
      <P>
        Teams running an agent in production who already have people reading its transcripts. If
        your reviewers are writing notes like &quot;promised a refund without checking the
        policy&quot; in a spreadsheet or a Slack thread, this puts those notes next to the exact
        step they refer to and makes them trainable.
      </P>
      <P>
        You don&apos;t need GPUs to start. The default base model is{" "}
        <Code>Qwen/Qwen3-0.6B</Code>, which trains on Apple silicon, a single CUDA GPU, or CPU,
        and the same job can run on a Modal A10G instead.
      </P>

      <H2>How the pieces fit</H2>
      <Table
        head={["Piece", "What it does"]}
        rows={[
          [
            <Link key="l" href="/reward-model-fine-tuning/trace-format" className="hover:text-brand">Format adapters</Link>,
            "Convert OpenAI, Anthropic, OpenTelemetry, Langfuse, LangSmith, Claude Code, and Codex exports into the Stash Trace Format.",
          ],
          [
            <Link key="l" href="/reward-model-fine-tuning/annotations" className="hover:text-brand">Annotations</Link>,
            "A rating (+1 / −1), a comment, or both, on a whole trace or one step, optionally anchored to a quoted span.",
          ],
          [
            <Link key="l" href="/reward-model-fine-tuning/training" className="hover:text-brand">Training worker</Link>,
            "A separate Python process (torch + transformers) that trains the reward model and scores every trace you own.",
          ],
          [
            <Link key="l" href="/reward-model-fine-tuning/gepa" className="hover:text-brand">GEPA runs</Link>,
            "Evolve a system prompt against your reward model, using your task model and reflection model.",
          ],
          [
            <Link key="l" href="/reward-model-fine-tuning/api" className="hover:text-brand">REST + SQL</Link>,
            "Everything is under /api/v1/rm, plus read-only DuckDB SQL over your own traces, steps, annotations, and scores.",
          ],
        ]}
      />
      <P>
        Reward model data is separate from Stash sessions. Traces you import here don&apos;t appear
        in your session history, and your sessions aren&apos;t imported here automatically.
      </P>

      <H2>Quickstart</H2>
      <P>Five minutes from a JSONL file to scored traces.</P>

      <H3>1. Point at your Stash</H3>
      <P>
        Set <Code>STASH_URL</Code> to the backend of the Stash instance you use. To run your own,
        see <Link href="/docs/self-hosting" className="text-brand hover:underline">Self-hosting</Link>{" "}
        and <Link href="/reward-model-fine-tuning/training#self-hosting-the-worker" className="text-brand hover:underline">Self-hosting the worker</Link>.
        Every request uses a bearer token; <Code>stash signin</Code> stores one:
      </P>
      <CodeBlock>{`export STASH_URL=http://localhost:3456   # your Stash backend
stash signin --api "$STASH_URL"
export STASH_API_KEY=$(jq -r .api_key ~/.stash/config.json)`}</CodeBlock>

      <H3>2. Import traces</H3>
      <P>
        Three traces in the <Link href="/reward-model-fine-tuning/trace-format" className="text-brand hover:underline">Stash Trace Format</Link>:
        two where the agent checks the refund policy, one where it doesn&apos;t.
      </P>
      <CodeBlock>{SAMPLE}</CodeBlock>
      <P>
        The import endpoint takes the file&apos;s contents as a string. <Code>auto</Code> detects the
        format, so the same command works for an OpenAI or Langfuse export.
      </P>
      <CodeBlock>{`jq -Rs '{format: "auto", data: .}' traces.jsonl \\
  | curl -s "$STASH_URL/api/v1/rm/traces/import" \\
      -H "Authorization: Bearer $STASH_API_KEY" \\
      -H "Content-Type: application/json" \\
      --data @-`}</CodeBlock>
      <CodeBlock>{`{"format": "stash", "imported": 3, "trace_ids": ["…", "…", "…"]}`}</CodeBlock>

      <H3>3. Annotate</H3>
      <P>
        Open <Code>/reward-models</Code> in the Stash app and pick a trace. Select text inside any step to comment on it, or rate the whole trace.
        For this example, give <Code>refund-1</Code> and <Code>refund-3</Code> a +, and give{" "}
        <Code>refund-2</Code> a − with the comment &quot;Promised a refund without checking the
        policy&quot;.
      </P>
      <Callout>
        Each + target is paired with each − target, and one pair is always held out for evaluation,
        so training needs at least two pairs: here, (refund-1, refund-2) and (refund-3, refund-2).
        With one + and one − there is only one pair, and the job fails.
      </Callout>

      <H3>4. Train</H3>
      <CodeBlock>{`curl -s "$STASH_URL/api/v1/rm/reward-models" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"name": "refund-policy", "compute": "local"}'`}</CodeBlock>
      <P>
        This trains the default base model, <Code>Qwen/Qwen3-0.6B</Code>, for one epoch on the
        machine running your Stash worker. The response is a reward model with{" "}
        <Code>status: &quot;queued&quot;</Code>. Poll it until it reaches <Code>succeeded</Code> or{" "}
        <Code>failed</Code>:
      </P>
      <CodeBlock>{`curl -s "$STASH_URL/api/v1/rm/reward-models/<id>" \\
  -H "Authorization: Bearer $STASH_API_KEY" | jq '{status, num_pairs, metrics, error}'`}</CodeBlock>

      <H3>5. Read the scores</H3>
      <P>
        When training finishes, the worker scores every trace you own, including ones nobody
        rated. Higher means closer to what your reviewers marked +. The trace view in the app shows
        each score, and the SQL endpoint returns them all at once:
      </P>
      <CodeBlock>{`curl -s "$STASH_URL/api/v1/rm/query" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"sql": "SELECT * FROM scores LIMIT 20"}'`}</CodeBlock>
      <P>
        From here, keep annotating and retrain, or hand the model to{" "}
        <Link href="/reward-model-fine-tuning/gepa" className="text-brand hover:underline">GEPA</Link> to
        optimize your system prompt against it.
      </P>

      <NextPage href="/reward-model-fine-tuning/trace-format" label="Trace format" />
    </>
  );
}
