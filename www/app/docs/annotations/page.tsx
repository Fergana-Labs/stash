import type { Metadata } from "next";

import { Code, CodeBlock, H2, H3, P, ParamTable, Title, Subtitle } from "../components";
import { NextPage, Table } from "../parts";

export const metadata: Metadata = {
  title: "Annotations · Stash Docs",
  description:
    "Comment on agent traces, anchor feedback to quoted spans, and see how comments, user corrections, and API ratings become training pairs.",
  alternates: { canonical: "/docs/annotations" },
};

const RENDERED = `user: I want a refund for order 1182

assistant → lookup_order({"order_id": "1182"})

tool: {"status": "delivered"}

assistant: Your order was delivered on May 3.`;

const RENDERED_TEXT_AND_CALL = `assistant: Let me check that order.
assistant → lookup_order({"order_id": "1182"})`;

const EXPORT_LINE = `{"trace_id": "…", "trace_external_id": "…", "step_index": 4, "rating": -1,
 "comment": "Promised a refund without checking the policy",
 "quote": {"text": "I've issued a full refund", "prefix": "Sure! ", "suffix": " to your card"},
 "label_error": false, "label_error_note": null, "author": "Henry Dowling",
 "created_at": "2026-09-29T03:12:00+00:00"}`;

export default function AnnotationsPage() {
  return (
    <>
      <Title>Annotations</Title>
      <Subtitle>
        Highlight a response and explain what should change. Comments and explicit user corrections can train reward models and guide skill generation.
      </Subtitle>

      <H2>What an annotation is</H2>
      <P>
        An annotation belongs to one trace and, optionally, one step in it. It carries a rating, a
        comment, or both. The UI creates comments; ratings are available through the API. A trace can have any number of annotations.
      </P>
      <ParamTable
        params={[
          { name: "step_id", type: "string | null", desc: "null annotates the whole trace. Set it to one of the trace's step ids to annotate that step." },
          { name: "rating", type: "1 | -1 | null", desc: "1 is +, −1 is −, null is a comment with no rating. Not allowed on system steps." },
          { name: "comment", type: "string | null", desc: "Free text. Actionable feedback can produce training pairs and is also sent to GEPA." },
          {
            name: "quote",
            type: "object | null",
            desc: "{text, prefix, suffix}: the highlighted span inside the step's content. Requires step_id, and text must appear in that step.",
          },
          { name: "label_error", type: "boolean", desc: "true when someone has flagged this annotation as wrong. Flagged annotations are excluded from training and GEPA." },
          { name: "label_error_note", type: "string | null", desc: "Why the label is wrong." },
        ]}
      />
      <P>
        An annotation needs a rating, a comment, or both. A request that breaks any of the rules in
        the table gets a <Code>422</Code> that says which one.
      </P>

      <H3>API ratings</H3>
      <P>
        Rate the whole trace when the outcome is what matters (&quot;resolved the ticket&quot;). Rate a
        step when one decision is the problem (&quot;called <Code>issue_refund</Code> before{" "}
        <Code>lookup_order</Code>&quot;). The two are trained as separate granularities and never paired
        against each other; see <a href="#from-annotations-to-training-pairs" className="text-brand hover:underline">training pairs</a> below.
      </P>

      <H3>System steps</H3>
      <P>
        You can comment on a system step but not rate it. The reward model never sees system steps:
        GEPA puts the skill it writes into the system message, and a reward model that read the
        system message could be satisfied by the skill&apos;s text rather than by what the agent does.
        Comments on a system prompt still reach GEPA as feedback, which is where they&apos;re useful.
      </P>

      <H3>Quoted spans</H3>
      <P>
        Select text inside a step in the app and the comment is anchored to it. The anchor is the
        selected <Code>text</Code> plus a short <Code>prefix</Code> and <Code>suffix</Code> from around it,
        the same scheme Stash uses for comments on pages. The surrounding context tells two identical
        phrases in the same step apart.
      </P>
      <CodeBlock lang="json">{`{"text": "I've issued a full refund", "prefix": "Sure! ", "suffix": " to your card"}`}</CodeBlock>
      <P>
        The quote&apos;s <Code>text</Code> must appear in the step&apos;s content, or the request fails
        with a <Code>422</Code>. The quote shows reviewers what the comment is about. A step-level
        rating applies to the whole step either way: training renders the step, not the quoted span.
      </P>

      <H3>Flagging label errors</H3>
      <P>
        Some labels are wrong. Instead of deleting the annotation, flag it with{" "}
        <Code>label_error: true</Code> and a note. The annotation stays visible in the trace, and
        training and GEPA skip it.
      </P>
      <CodeBlock lang="bash">{`curl -s -X PATCH "$STASH_URL/api/v1/rm/annotations/<annotation_id>" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"label_error": true, "label_error_note": "Policy allows refunds on damaged items"}'`}</CodeBlock>
      <P>
        On each trace summary, <Code>label_error_count</Code> counts flagged annotations, and{" "}
        <Code>positive_count</Code> / <Code>negative_count</Code> leave them out. These count explicit API ratings; feedback-derived pairs are not included.
      </P>

      <H2>Annotating over the API</H2>
      <P>
        Get step ids from <Code>GET /traces/&#123;trace_id&#125;</Code>, then post one annotation per
        call. Omit <Code>step_id</Code> to annotate the whole trace. The response is the stored
        annotation, with its <Code>id</Code>, <Code>author_id</Code>, <Code>author_name</Code>, and{" "}
        <Code>created_at</Code>.
      </P>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/traces/<trace_id>/annotations" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "step_id": "<step_id>",
    "comment": "Promised a refund without checking the policy",
    "quote": {"text": "I'"'"'ve issued a full refund", "prefix": "Sure! ", "suffix": " to your card"}
  }'`}</CodeBlock>
      <P>
        This is also how to load labels you already have: import the traces, then post their existing
        ratings as annotations.
      </P>

      <H2>From annotations to training pairs</H2>
      <P>
        The reward model trains on preference pairs: one text that should score higher (chosen) and
        one that should score lower (rejected). Only the model&apos;s selected traces supply pairs.
        There are two sources: feedback-derived alternatives and explicit API ratings.
      </P>

      <H3>Comments and user corrections</H3>
      <P>
        The worker uses a model to identify explicit, actionable feedback about an assistant response
        and generate an alternative to the same context. Each pair records which response the feedback
        prefers, the source ID, a verbatim evidence quote, and a rationale. These are interpretations
        of feedback, not direct human preference votes.
      </P>
      <P>
        Silence, a new question, or a tool error is not a preference. Ambiguous feedback is skipped.
        The cited source must exist, a user correction must follow the response, and a step comment
        must refer to that response. Tool calls and system steps cannot be revision targets.
        Malformed extraction fails the job. Flagged comments are excluded.
      </P>
      <P>
        Both responses share the original conversation prefix. System steps and later messages,
        including the correction, are excluded from the training text. The exact pairs and evidence
        are persisted with the model. Training combines API-rating pairs followed by feedback pairs,
        caps them at <Code>max_pairs</Code> (default 4000), and requires at least two usable pairs.
      </P>

      <H3>Explicit API ratings</H3>
      <P>Ratings supplied through the API produce pairs as follows:</P>

      <H3>1. Drop flagged annotations</H3>
      <P>Every annotation with <Code>label_error = true</Code> is removed before anything else.</P>

      <H3>2. Collapse ratings per target</H3>
      <P>
        A target is a whole trace or a single step. Its ratings are summed. A positive sum makes it
        chosen, a negative sum makes it rejected, and zero skips it. Opposite ratings cancel out.
      </P>
      <Table
        head={["target", "ratings", "sum", "result"]}
        rows={[
          ["trace A", "+1, +1", "+2", "chosen"],
          ["trace B", "−1", "−1", "rejected"],
          ["trace C", "+1, −1", "0", "skipped"],
          ["trace D, step 4", "−1", "−1", "rejected"],
          ["trace E, step 2", "+1, +1, −1", "+1", "chosen"],
        ]}
      />

      <H3>3. Render each target to text</H3>
      <P>
        A trace renders all of its steps except system steps. A step renders the trace&apos;s steps
        up to and including itself, again without system steps, so the model sees the context the
        agent had. Each step is <Code>&lt;role&gt;: &lt;content&gt;</Code>, steps are joined with blank
        lines, and tool calls are written as{" "}
        <Code>assistant → &lt;tool_name&gt;(&lt;tool_input json&gt;)</Code>. The trace on{" "}
        <a href="/docs/trace-format#stash-trace-format" className="text-brand hover:underline">Trace format</a>{" "}
        renders as:
      </P>
      <CodeBlock lang="text">{RENDERED}</CodeBlock>
      <P>An assistant step with both text and a tool call renders both lines, text first:</P>
      <CodeBlock lang="text">{RENDERED_TEXT_AND_CALL}</CodeBlock>

      <H3>4. Pair within the same granularity</H3>
      <P>
        Every chosen target is paired with every rejected target of the same granularity: traces with
        traces, steps with steps. In the table above that gives two pairs: (A, B) and (E step 2, D
        step 4). The pairs are shuffled with seed 0 and capped at <Code>max_pairs</Code> (default
        4000), so the same labels always produce the same training set.
      </P>

      <H2>Exporting annotations</H2>
      <P>
        <Code>GET /api/v1/rm/export/annotations</Code> returns one annotation per line. Flagged
        annotations are included, with <Code>label_error: true</Code>, so the export is a complete
        record.
      </P>
      <CodeBlock lang="json">{EXPORT_LINE}</CodeBlock>
      <ParamTable
        params={[
          { name: "trace_id", type: "string", desc: "Stash's id for the trace." },
          { name: "trace_external_id", type: "string | null", desc: "The id you imported the trace with." },
          { name: "step_index", type: "integer | null", desc: "Position of the step in the trace, or null for a trace-level annotation." },
          { name: "rating", type: "1 | -1 | null", desc: "+1, −1, or no rating." },
          { name: "comment", type: "string | null", desc: "The reviewer's comment." },
          { name: "quote", type: "object | null", desc: "{text, prefix, suffix}." },
          { name: "label_error", type: "boolean", desc: "Whether the annotation is flagged as wrong." },
          { name: "label_error_note", type: "string | null", desc: "Why it was flagged." },
          { name: "author", type: "string", desc: "The name of the user who wrote it." },
          { name: "created_at", type: "string", desc: "ISO 8601." },
        ]}
      />

      <NextPage href="/docs/implementation" label="Implementation" />
    </>
  );
}
