import type { Metadata } from "next";
import Link from "next/link";

import { Code, CodeBlock, H2, P, Title } from "../components";
import { NextPage } from "../parts";

export const metadata: Metadata = {
  title: "Implementation · Stash Docs",
  description:
    "How Stash turns trace files and annotations into a Bradley–Terry reward model, calibrated scores, and a GEPA-written skill.",
  alternates: { canonical: "/docs/implementation" },
};

const FLOW = `import   trace file ─ adapter ─▶ traces, steps
annotate annotations ─────────▶ annotations

train    selected feedback ─ pairs.jsonl ─ rm_worker ─▶ private S3 checkpoint, scores
skill    gepa_examples.jsonl ─ rm_worker ─▶ SKILL.md

query    your rows ─▶ in-memory DuckDB ─▶ result`;

const link = "text-brand hover:underline";

export default function ImplementationPage() {
  return (
    <>
      <Title>Implementation</Title>
      <P>
        The backend stores traces, annotations, and training evidence in Postgres. A dedicated
        reward worker extracts preferences through a model-provider API, then dispatches training
        and skill generation to <Code>rm_worker</Code>. GPU libraries run in a local ML environment
        or inside Modal; the API never imports torch.
      </P>
      <CodeBlock lang="text">{FLOW}</CodeBlock>
      <P>
        This data is separate from Stash sessions: traces imported here don&apos;t appear in your
        session history, and sessions aren&apos;t imported here.
      </P>

      <H2>Import</H2>
      <P>
        Each input format has an adapter that converts a file into the Stash Trace Format: a list of
        steps with a <Code>role</Code> of system, user, assistant, or tool. A tool call becomes an
        assistant step with <Code>tool_name</Code> and <Code>tool_input</Code>; its result becomes a tool
        step with the same <Code>tool_call_id</Code>. Formats that log one entry per LLM call
        (OpenTelemetry, Langfuse, LangSmith) are joined into one conversation by dropping the history
        each call re-sends. An import is parsed completely before anything is stored, so it either
        stores every trace or none. Details:{" "}
        <Link href="/docs/trace-format" className={link}>Trace format</Link>.
      </P>

      <H2>Annotations to preference pairs</H2>
      <P>
        Training uses only selected traces. Comments and explicit later user corrections can
        produce an original/revised response pair with a shared context and cited evidence. The
        model-generated revision and preference are interpretations of feedback, not direct human votes.
        Ambiguous feedback is skipped; invalid extraction fails the job. Explicit API ratings also
        produce pairs: Stash drops
        annotations flagged as label errors, sums the ratings on each trace and each step, and calls a
        target chosen if its sum is positive and rejected if negative. Each target is rendered as{" "}
        <Code>&lt;role&gt;: &lt;content&gt;</Code> lines without system steps; a step target includes
        the steps before it. Every chosen target is paired with every rejected target of the same kind
        (trace with trace, step with step), shuffled with seed 0, and capped at 4000 pairs. Details:{" "}
        <Link href="/docs/annotations#from-annotations-to-training-pairs" className={link}>Annotations</Link>.
      </P>

      <H2>Training</H2>
      <P>
        A training job runs on the dedicated Celery <Code>reward</Code> exchange/queue. The backend writes the pairs and
        the traces to score into a job directory under <Code>RM_ARTIFACT_DIR</Code>, runs{" "}
        <Code>rm_worker</Code> with <Code>RM_WORKER_PYTHON</Code>, and reads the results back. The worker
        fine-tunes the base model (<Code>Qwen/Qwen3-0.6B</Code> by default) as a single-output
        classifier with the Bradley–Terry loss <Code>−log σ(r(chosen) − r(rejected))</Code>, holding out
        10% of pairs to report accuracy. It runs on MPS, CUDA, or CPU on the worker machine, or on a
        Modal A10G. Details: <Link href="/docs/training" className={link}>Training</Link>.
      </P>

      <H2>Scoring</H2>
      <P>
        After training, the worker scores every trace the owner has, and those raw rewards are what the
        app and the API show, attributed to their model. Separately, it scores both chosen and
        rejected texts from the training and held-out pairs and saves their mean and standard deviation in{" "}
        <Code>model/reward_stats.json</Code>. GEPA uses them to calibrate each reward to{" "}
        <Code>sigmoid((reward − mean) / std)</Code>, so 0.5 corresponds to the calibration mean and a good reply still
        has room to score higher. Details:{" "}
        <Link href="/docs/gepa#the-calibrated-score" className={link}>The calibrated score</Link>.
      </P>

      <H2>Skill writing (GEPA)</H2>
      <P>
        Each selected trace with replayable input becomes an example: its own system prompt, plus the non-system steps before
        the agent&apos;s first reply. For each candidate skill, the worker calls your task model with the
        system prompt and the skill in the system message, scores the reply with the reward model, and
        sends the score, unflagged comments, and recorded feedback evidence to a reflection model, which writes the next
        skill body. The reward model never sees the system message, so a skill can only raise its score
        by changing what the agent says. The result is the highest-scoring skill. Details:{" "}
        <Link href="/docs/gepa" className={link}>Skills (GEPA)</Link>.
      </P>

      <H2>Checkpoint storage</H2>
      <P>
        Training uploads a private S3 checkpoint before succeeding. The API authorizes a five-minute
        download URL; GEPA downloads that checkpoint into a fresh temporary workspace. The API never
        needs access to the training worker&apos;s filesystem. Modal returns only JSON results and
        scores, and receives no database or queue credentials.
      </P>

      <H2>REST and SQL</H2>
      <P>
        Everything is under <Code>/api/v1/rm</Code> with bearer auth, and every row belongs to one user. Accounts outside the new-account experiment receive 404 from every reward-model endpoint.
        The SQL endpoint loads only the caller&apos;s traces, steps, annotations, and scores into a new
        in-memory DuckDB per query, with file and network access turned off, a 1000-row cap, and a
        10-second limit. Details: <Link href="/docs/api" className={link}>API reference</Link>.
      </P>

      <NextPage href="/docs/training" label="Training" />
    </>
  );
}
