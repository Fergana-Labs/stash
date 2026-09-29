import type { Metadata } from "next";
import Link from "next/link";

import { Code, CodeBlock, H2, P, Title } from "./components";
import { DemoClip, NextPage, Pipeline } from "./parts";

export const metadata: Metadata = {
  title: "Stash Docs",
  description:
    "Annotate agent traces with + / − comments, train a reward model from them, and use it to post-train or to write a skill for your agent with GEPA.",
  alternates: { canonical: "/docs" },
};

const CONNECT = `export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.joinstash.ai/api/v1/rm/otel
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer%20$STASH_API_KEY"

opentelemetry-instrument python agent.py`;

const INSTALL = `pip install opentelemetry-distro \\
  opentelemetry-exporter-otlp-proto-http \\
  openinference-instrumentation-anthropic`;

const ONE_SPAN = `with tracer.start_as_current_span("agent-run"):
    run_agent(task)`;

// Excerpt of the skill produced in skill.mp4.
const SKILL_EXAMPLE = `---
name: refund-requests
description: Use this skill whenever a user requests a refund
  or reports a broken/damaged order. Always look up the order
  details and check the applicable refund policy before
  responding, and explain the next steps to the user rather
  than promising a refund outright.
---

## Hard rules

- **Never** promise a refund, replacement, or specific dollar
  amount as a done deal before eligibility is confirmed.
- **Never** claim to have looked something up that you did
  not actually look up.
- **Never** ask the user to repeat information already given
  in the conversation.`;

export default function RewardModelsOverviewPage() {
  return (
    <>
      <Title>Overview</Title>
      <P>
        Stash makes it easy to annotate traces so that you can emphasize what you wish the agent would
        have done better. Once you submit your annotations, Stash converts that into an easy-to-use reward
        model that you can use to either post-train or prompt-optimize with GEPA.
      </P>
      <Pipeline />

      <H2>1. Connect Stash to your agent</H2>
      <P>
        Stash reads your agent&apos;s traces over OpenTelemetry. Install the instrumentation for your
        framework, set three variables, and every run shows up on the Traces page.
      </P>
      <CodeBlock lang="bash">{CONNECT}</CodeBlock>
      <DemoClip src="/docs/demo/connect.mp4" />
      <P>
        The instrumentation for an Anthropic agent, for example (the{" "}
        <Link href="https://github.com/Arize-ai/openinference" className="text-brand hover:underline">OpenInference</Link>{" "}
        packages cover OpenAI, the OpenAI Agents SDK, LangChain, LlamaIndex, CrewAI, DSPy, Bedrock, and
        more; the Vercel AI SDK emits OpenTelemetry on its own):
      </P>
      <CodeBlock lang="bash">{INSTALL}</CodeBlock>
      <P>
        Frameworks group each run into one trace. If your agent calls a model SDK directly in a loop,
        wrap each run in a span so its calls land in the same trace:
      </P>
      <CodeBlock lang="python">{ONE_SPAN}</CodeBlock>

      <H2>2. Annotate them</H2>
      <P>
        Open a trace and mark it, or any step in it, + or −. To say what went wrong, highlight the text
        and leave a comment.
      </P>
      <DemoClip src="/docs/demo/annotate.mp4" />

      <H2>3. Train a reward model</H2>
      <P>
        On the Reward models tab, press <strong>Train reward model</strong>. Stash trains a reward model
        on your + and − marks and scores every trace, including the ones nobody annotated. Download the
        weights to use the model as the reward function when you post-train.
      </P>
      <DemoClip src="/docs/demo/train.mp4" />

      <H2>4. Write a skill</H2>
      <P>
        On a trained reward model, press <strong>Create skill</strong>. GEPA reads your comments, writes a{" "}
        <Code>SKILL.md</Code> that teaches your agent to score well on that reward model, and names it.
        Your agent loads the skill next to its system prompt, which Stash leaves alone.
      </P>
      <DemoClip src="/docs/demo/skill.mp4" />
      <P>An excerpt from the skill in that recording:</P>
      <CodeBlock lang="markdown">{SKILL_EXAMPLE}</CodeBlock>

      <NextPage href="/docs/trace-format" label="Trace format" />
    </>
  );
}
