import type { Metadata } from "next";

import { Callout, Code, CodeBlock, CodeTabs, H2, H3, P, ParamTable, Title, Subtitle } from "../components";
import { NextPage, Table } from "../parts";

export const metadata: Metadata = {
  title: "GEPA · Stash Reward Models",
  description:
    "Optimize an agent's system prompt with GEPA, using your reviewers' comments as feedback and your trained reward model as the metric. Works with any OpenAI-compatible endpoint.",
  alternates: { canonical: "/docs/gepa" },
};

export default function GepaPage() {
  return (
    <>
      <Title>GEPA prompt optimization</Title>
      <Subtitle>
        Rewrite your system prompt against your reward model, with your reviewers&apos; comments as the feedback.
      </Subtitle>

      <H2>What GEPA is</H2>
      <P>
        GEPA is a prompt optimizer from Agrawal et al., 2025,{" "}
        <a href="https://arxiv.org/abs/2507.19457" className="text-brand hover:underline">
          &quot;GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning&quot;
        </a>{" "}
        (arXiv 2507.19457). It improves a prompt in a loop:
      </P>
      <ol className="my-6 space-y-3 border-l border-border-subtle pl-5 text-[15px] leading-7 text-dim">
        <li><span className="mr-3 font-mono text-[12px] text-muted">01</span>Run the current prompt on some examples.</li>
        <li><span className="mr-3 font-mono text-[12px] text-muted">02</span>Collect a score and written feedback for each result.</li>
        <li><span className="mr-3 font-mono text-[12px] text-muted">03</span>Ask a reflection model to read the feedback and propose a better prompt.</li>
        <li><span className="mr-3 font-mono text-[12px] text-muted">04</span>Keep a Pareto front of candidates: any prompt that is best on at least one example survives.</li>
      </ol>
      <P>
        Written feedback is what separates it from optimizers that only see a number. A comment like
        &quot;promised a refund without checking the policy&quot; tells the reflection model what to change,
        not only that something went wrong.
      </P>

      <H2>How Stash wires it up</H2>
      <Table
        head={["GEPA needs", "Stash provides"]}
        rows={[
          [
            "examples",
            "Every trace you own with at least one annotation that isn't flagged as a label error. The input is the trace's steps before its first assistant step, minus system steps.",
          ],
          ["candidate", <>One text field, <Code key="c">system_prompt</Code>, seeded with the prompt you pass. It takes the place of the trace&apos;s system step.</>],
          ["task model", "Called once per example: the candidate as the system message, then the example's input. The reply is one assistant message; no tools are passed."],
          ["metric", "sigmoid(reward) from your reward model on the input plus the reply, so every score is between 0 and 1."],
          ["feedback", "The score, every comment annotators left on that trace, and the task model's error if the request failed."],
        ]}
      />
      <P>
        The scored text is rendered like training text (see{" "}
        <a href="/docs/annotations#3-render-each-target-to-text" className="text-brand hover:underline">Annotations</a>),
        and it leaves out the system prompt. That matters here more than anywhere: if the reward model
        read the candidate prompt, GEPA could raise its score by writing what the reward model likes into
        the prompt, without changing what the agent says.
      </P>
      <P>
        The comments come from the original trace. They describe what went wrong last time, which is
        what the reflection model needs to write the next prompt. The reflection model sees them as:
      </P>
      <CodeBlock>{`Reward model score: 0.214 (0 to 1, higher is better)
Human reviewer comment: Promised a refund without checking the policy`}</CodeBlock>
      <P>
        A trace with no input before its first assistant step has nothing to replay, so it is skipped.
        If no examples are left, the run fails with{" "}
        <Code>need at least one annotated trace with a user turn</Code>.
      </P>
      <Callout>
        Traces with only ratings still count as examples; their feedback is the score alone.
        Traces with comments give the reflection model much more to work with.
      </Callout>

      <H2>Start a run</H2>
      <P>
        You need one of your reward models with status <Code>succeeded</Code>. Another user&apos;s
        model is a <Code>404</Code>; one that hasn&apos;t finished training is a <Code>422</Code>.
      </P>
      <CodeBlock>{`curl -s "$STASH_URL/api/v1/rm/gepa-runs" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "reward_model_id": "<reward_model_id>",
    "seed_prompt": "You are a support agent for Acme. Be concise.",
    "task_model": "openai/gpt-4.1-mini",
    "reflection_model": "anthropic/claude-sonnet-5"
  }'`}</CodeBlock>
      <ParamTable
        params={[
          { name: "reward_model_id", type: "string", desc: "A trained reward model. It is the metric.", required: true },
          { name: "seed_prompt", type: "string", desc: "The system prompt to start from. Usually the one your agent runs today.", required: true },
          { name: "task_model", type: "string", desc: "LiteLLM model string for the model your agent runs on.", required: true },
          { name: "task_api_base", type: "string", desc: "Base URL for an OpenAI-compatible server. Use with an openai/<name> task_model." },
          { name: "reflection_model", type: "string", desc: "LiteLLM model string for the model that reads feedback and writes new prompts.", required: true },
          { name: "max_metric_calls", type: "integer", desc: "Budget: how many example evaluations GEPA may run, each one a task model call plus a reward model score. Default 150." },
        ]}
      />
      <P>
        Use the model your agent actually runs on as <Code>task_model</Code>, so the prompt is tuned for
        it. Use a strong model as <Code>reflection_model</Code>; it writes every candidate.
      </P>
      <P>
        Both are called through LiteLLM, which reads the standard provider keys{" "}
        (<Code>ANTHROPIC_API_KEY</Code>, <Code>OPENAI_API_KEY</Code>, …) from the worker&apos;s
        environment. A vLLM or SGLang server set as <Code>task_api_base</Code> needs no key unless
        you started it with one.
      </P>

      <H2>Your own model as the task model</H2>
      <P>
        Any OpenAI-compatible server works, including vLLM and SGLang. Serve your model, then pass{" "}
        <Code>openai/&lt;served model name&gt;</Code> as <Code>task_model</Code> and the server&apos;s{" "}
        <Code>/v1</Code> URL as <Code>task_api_base</Code>.
      </P>
      <CodeTabs
        tabs={[
          {
            label: "vLLM",
            code: `vllm serve Qwen/Qwen3-8B --port 8000

# in the run request:
"task_model": "openai/Qwen/Qwen3-8B",
"task_api_base": "http://gpu-box.internal:8000/v1"`,
          },
          {
            label: "SGLang",
            code: `python -m sglang.launch_server --model-path Qwen/Qwen3-8B --port 30000

# in the run request:
"task_model": "openai/Qwen/Qwen3-8B",
"task_api_base": "http://gpu-box.internal:30000/v1"`,
          },
        ]}
      />
      <Callout type="warning">
        The task model is called from wherever the Stash worker runs, not from your laptop. The{" "}
        <Code>task_api_base</Code> URL must be reachable from there.
      </Callout>

      <H2>Reading the results</H2>
      <CodeBlock>{`curl -s "$STASH_URL/api/v1/rm/gepa-runs/<id>" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  | jq '{status, seed_score, best_score, best_prompt}'`}</CodeBlock>
      <Table
        head={["field", "meaning"]}
        rows={[
          ["status", "queued, running, succeeded, or failed."],
          ["seed_score", "Your seed prompt's mean score over all examples."],
          ["best_score", "The best candidate's mean score over all examples."],
          ["best_prompt", "The candidate with the highest mean score."],
          ["candidates", "Every prompt tried, with its mean score: [{prompt, score}]. The seed is first."],
          ["error", "Why the run failed, when status is failed."],
        ]}
      />
      <P>
        Scores are means of <Code>sigmoid(reward)</Code>, between 0 and 1. Compare{" "}
        <Code>best_score</Code> to <Code>seed_score</Code>: both come from the same reward model on the
        same examples, so the difference is what the new prompt bought you. Annotated traces are
        usually few, so every example is used both to propose prompts and to rank them. Treat the gain
        as an in-sample number, not a held-out one.
      </P>

      <H3>When a run fails</H3>
      <P>
        If the task model rejects one example&apos;s request, that example scores 0 and the error goes
        to the reflection model as feedback, so the run continues. Authentication, rate-limit, and
        connection errors from the task model fail the run, and so does any error from the reflection
        model. <Code>error</Code> on the run holds the end of the worker&apos;s log.
      </P>

      <H3>Before you ship the prompt</H3>
      <P>
        GEPA optimizes whatever your reward model rewards, including its mistakes. Read{" "}
        <Code>best_prompt</Code> and a few of the <Code>candidates</Code> before deploying one. If the
        winning prompt games something your reviewers wouldn&apos;t approve of, run the new prompt, import
        the resulting traces, annotate them, and retrain. Each round of labels closes a gap the last
        model left open.
      </P>

      <NextPage href="/docs/api" label="API reference" />
    </>
  );
}
