import type { Metadata } from "next";

import { Callout, Code, CodeBlock, CodeTabs, H2, H3, P, ParamTable, Title, Subtitle } from "../components";
import { NextPage, Table } from "../parts";

export const metadata: Metadata = {
  title: "Skills (GEPA) · Stash Docs",
  description:
    "Write a SKILL.md for your agent with GEPA, using your reviewers' comments as feedback and your trained reward model as the metric. Works with any OpenAI-compatible endpoint.",
  alternates: { canonical: "/docs/gepa" },
};

const SKILL_EXAMPLE = `---
name: refund-policy
description: Use when a customer asks for a refund, return, or exchange.
---

Before promising a refund, look the order up with lookup_order and check
days_since_delivery. Refunds are allowed within 30 days of delivery.
Past 30 days, say so plainly and offer store credit instead.`;

const SYSTEM_MESSAGE = `<the example's own system prompt, when it has one>

<skill name="refund-policy">
---
name: refund-policy
description: Use when a customer asks for a refund, return, or exchange.
---

<candidate skill body>
</skill>`;

export default function GepaPage() {
  return (
    <>
      <Title>Skills (GEPA)</Title>
      <Subtitle>
        Turn your reviewers&apos; comments into a skill your agent loads, scored by your reward model.
      </Subtitle>

      <H2>What you get</H2>
      <P>
        A GEPA run produces a skill: a <Code>SKILL.md</Code> file with YAML frontmatter (
        <Code>name</Code> and <Code>description</Code>) followed by Markdown instructions. Your agent
        loads it into its context. Your agent&apos;s own system prompt is never rewritten.
      </P>
      <CodeBlock lang="markdown">{SKILL_EXAMPLE}</CodeBlock>
      <P>
        The reflection model generates the name and description from the selected traces and their
        feedback. The description says when to use the skill and becomes its seed body; GEPA then
        evolves the body. In the app, <strong>View skill</strong> opens an existing run or starts one.
      </P>

      <H2>What GEPA is</H2>
      <P>
        GEPA is an optimizer for text, from Agrawal et al., 2025,{" "}
        <a href="https://arxiv.org/abs/2507.19457" className="text-brand hover:underline">
          &quot;GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning&quot;
        </a>{" "}
        (arXiv 2507.19457). It improves text in a loop:
      </P>
      <ol className="my-6 space-y-3 border-l border-border-subtle pl-5 text-[15px] leading-7 text-dim">
        <li><span className="mr-3 font-mono text-[12px] text-muted">01</span>Run the agent with the current text on some examples.</li>
        <li><span className="mr-3 font-mono text-[12px] text-muted">02</span>Collect a score and written feedback for each result.</li>
        <li><span className="mr-3 font-mono text-[12px] text-muted">03</span>Ask a reflection model to read the feedback and propose better text.</li>
        <li><span className="mr-3 font-mono text-[12px] text-muted">04</span>Keep a Pareto front of candidates: any text that is best on at least one example survives.</li>
      </ol>
      <P>
        Written feedback is what separates it from optimizers that only see a number. A comment like
        &quot;promised a refund without checking the policy&quot; tells the reflection model what to change,
        not only that something went wrong. In Stash, the text GEPA evolves is the skill&apos;s body.
      </P>

      <H2>How Stash wires it up</H2>
      <Table
        head={["GEPA needs", "Stash provides"]}
        rows={[
          [
            "examples",
            "The traces selected for the reward model, whether or not they have annotations. Each keeps its own system prompt (its system steps joined, or none) and its input: the non-system steps before the first assistant step.",
          ],
          [
            "candidate",
            <>One text field, the skill body. The seed body is the generated <Code key="c">skill_description</Code> as a single line.</>,
          ],
          [
            "task model",
            "Called once per example: a system message holding the example's own system prompt and the rendered skill, then the example's input.",
          ],
          ["metric", "Your reward model's reward for the conversation, reply included, calibrated to a score between 0 and 1. See below."],
          ["feedback", "The score, unflagged comments, and recorded evidence from feedback-derived training pairs."],
        ]}
      />
      <P>
        The task model&apos;s system message is the example&apos;s own system prompt, a blank line, then
        the skill. A trace with no system steps gets the skill block alone.
      </P>
      <CodeBlock lang="text">{SYSTEM_MESSAGE}</CodeBlock>
      <P>
        The conversation the reward model scores is rendered like training text (see{" "}
        <a href="/docs/annotations#3-render-each-target-to-text" className="text-brand hover:underline">Annotations</a>),
        without the system message. That is why the reward model never sees system steps: the skill
        is in the system message, and if the reward model read it, GEPA could raise its score by writing
        what the reward model likes into the skill without changing what the agent does.
      </P>
      <P>
        The comments come from the original trace. They describe what went wrong last time, which is
        what the reflection model needs to write the next version. It is told that it is writing the
        body of a <Code>SKILL.md</Code> and must return only the body; the name and description stay
        fixed for the whole run.
      </P>
      <H3>The calibrated score</H3>
      <P>GEPA&apos;s score for one example is</P>
      <CodeBlock lang="text">{`score = sigmoid( (reward − mean) / std )`}</CodeBlock>
      <P>
        where <Code>mean</Code> and <Code>std</Code> are the mean and standard deviation of the reward
        model&apos;s scores over both chosen and rejected texts in the training and held-out pairs,
        saved in <Code>reward_stats.json</Code> inside the checkpoint. A score of 0.5 corresponds to
        that calibration mean; higher is better. It is not a probability of correctness. Raw rewards are the wrong scale for this: a confident reward model
        gives a decent reply a raw <Code>sigmoid(reward)</Code> of about 0.99, which leaves GEPA no room
        to tell a better skill from the seed.
      </P>
      <P>
        GEPA downloads the private checkpoint into a fresh temporary workspace. It uses the same
        runtime recorded on the reward model; it does not need the original training filesystem.
      </P>
      <P>
        A trace with no input before its first assistant step has nothing to replay, so it is skipped.
        If no examples are left, the run fails.
      </P>

      <H2>Start a run</H2>
      <P>
        You need one of your reward models with status <Code>succeeded</Code>. Another user&apos;s
        model is a <Code>404</Code>; one that hasn&apos;t finished training is a <Code>422</Code>.
      </P>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/gepa-runs" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "reward_model_id": "<reward_model_id>",
    "task_model": "openai/gpt-4.1-mini",
    "reflection_model": "anthropic/claude-sonnet-5"
  }'`}</CodeBlock>
      <ParamTable
        params={[
          { name: "reward_model_id", type: "string", desc: "A trained reward model. It is the metric.", required: true },
          { name: "task_model", type: "string", desc: "LiteLLM task model. Default anthropic/claude-haiku-4-5." },
          { name: "task_api_base", type: "string", desc: "Base URL for an OpenAI-compatible server. Use with an openai/<name> task_model." },
          { name: "reflection_model", type: "string", desc: "Model that writes skill bodies. Default anthropic/claude-sonnet-5." },
          { name: "max_metric_calls", type: "integer", desc: "Budget: how many example evaluations GEPA may run, each one a task model call plus a reward model score. Default 40." },
        ]}
      />
      <P>
        Use the model your agent actually runs on as <Code>task_model</Code>, so the skill is tuned for
        it. Use a strong model as <Code>reflection_model</Code>; it generates the skill identity
        and writes every candidate body.
      </P>
      <P>
        Both models are called through LiteLLM, which reads the standard provider keys{" "}
        from the worker&apos;s environment. The Modal runner forwards <Code>ANTHROPIC_API_KEY</Code>{" "}
        and <Code>OPENAI_API_KEY</Code>; other providers need explicit runner configuration. A vLLM or SGLang server set as <Code>task_api_base</Code> needs no key unless
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
            lang: "bash",
            code: `vllm serve Qwen/Qwen3-8B --port 8000

# in the run request:
"task_model": "openai/Qwen/Qwen3-8B",
"task_api_base": "http://gpu-box.internal:8000/v1"`,
          },
          {
            label: "SGLang",
            lang: "bash",
            code: `python -m sglang.launch_server --model-path Qwen/Qwen3-8B --port 30000

# in the run request:
"task_model": "openai/Qwen/Qwen3-8B",
"task_api_base": "http://gpu-box.internal:30000/v1"`,
          },
        ]}
      />
      <Callout type="warning">
        The task model is called from the local worker or Modal GPU process, according to the model&apos;s runtime. The{" "}
        <Code>task_api_base</Code> URL must be reachable from there.
      </Callout>

      <H2>Reading the results</H2>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/gepa-runs/<id>" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  | jq '{status, seed_score, best_score}'`}</CodeBlock>
      <Table
        head={["field", "meaning"]}
        rows={[
          ["status", "queued, running, succeeded, or failed."],
          ["seed_skill", "The starting SKILL.md, with the description as its body."],
          ["seed_score", "The seed skill's mean score over all examples."],
          ["best_skill", "The full SKILL.md with the highest mean score."],
          ["best_score", "Its mean score over all examples."],
          ["candidates", "Every skill tried, as a full SKILL.md, with its mean score: [{skill, score}]."],
          ["error", "Why the run failed, when status is failed."],
        ]}
      />
      <P>
        Scores are means of the <a href="#the-calibrated-score" className="text-brand hover:underline">calibrated score</a>,
        between 0 and 1, where 0.5 is the calibration mean. Compare{" "}
        <Code>best_score</Code> to <Code>seed_score</Code>: both come from the same reward model on the
        same examples, so the difference is what the skill bought you. Selected traces are often
        few, so every example is used both to propose skills and to rank them. Treat the gain as an
        in-sample number, not a held-out one.
      </P>

      <H3>Install the skill</H3>
      <P>
        Download the best skill as <Code>SKILL.md</Code>. Until the run succeeds, this is a{" "}
        <Code>404</Code>.
      </P>
      <CodeBlock lang="bash">{`mkdir -p .claude/skills/refund-policy
curl -s "$STASH_URL/api/v1/rm/gepa-runs/<id>/skill" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -o .claude/skills/refund-policy/SKILL.md`}</CodeBlock>
      <P>
        That path is where Claude Code looks for project skills. For another agent, put the file wherever
        it loads skills or instructions from.
      </P>

      <H3>When a run fails</H3>
      <P>
        If the task model rejects one example&apos;s request, that example scores 0 and the error goes
        to the reflection model as feedback, so the run continues. Authentication, rate-limit, and
        connection errors from the task model fail the run, and so does any error from the reflection
        model. A run where the reflection model was never called also fails, usually because{" "}
        <Code>max_metric_calls</Code> ran out while evaluating the seed skill. <Code>error</Code> on
        the run holds the end of the worker&apos;s log.
      </P>

      <H3>Before you ship the skill</H3>
      <P>
        GEPA optimizes whatever your reward model rewards, including its mistakes. Read{" "}
        <Code>best_skill</Code> and a few of the <Code>candidates</Code> before deploying one. If the
        winning skill games something your reviewers wouldn&apos;t approve of, run the agent with it,
        import the resulting traces, annotate them, and retrain. Each round of labels closes a gap the
        last model left open.
      </P>

      <NextPage href="/docs/api" label="API reference" />
    </>
  );
}
