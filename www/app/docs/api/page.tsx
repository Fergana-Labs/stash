import type { Metadata } from "next";

import { Callout, Code, CodeBlock, CodeTabs, H2, H3, P, ParamTable, Title, Subtitle } from "../components";
import { Endpoint, Table } from "../parts";

export const metadata: Metadata = {
  title: "API Reference · Stash Docs",
  description:
    "REST reference for /api/v1/rm: import traces, annotate, export, train reward models, write skills with GEPA, and query your data with read-only DuckDB SQL.",
  alternates: { canonical: "/docs/api" },
};

const AUTH = `-H "Authorization: Bearer $STASH_API_KEY"`;
const JSON_HEADERS = `${AUTH} \\
  -H "Content-Type: application/json"`;

const NEGATIVE_RATE_SQL = `SELECT s.tool_name,
       count(*)                                        AS rated_steps,
       avg(CASE WHEN a.rating = -1 THEN 1 ELSE 0 END)  AS negative_rate
FROM annotations a
JOIN steps s ON s.id = a.step_id
WHERE a.rating IS NOT NULL
  AND NOT a.label_error
  AND s.tool_name IS NOT NULL
GROUP BY s.tool_name
ORDER BY negative_rate DESC`;

export default function RewardModelsApiPage() {
  return (
    <>
      <Title>API reference</Title>
      <Subtitle>
        Everything in the reward model app is available over REST under <Code>/api/v1/rm</Code>.
      </Subtitle>

      <H2>Authentication</H2>
      <P>
        Send a Stash API key as a bearer token. Create one on the{" "}
        <a href="https://app.joinstash.ai/developer/keys" className="text-brand hover:underline">API Keys</a>{" "}
        page. Every endpoint reads and writes only the caller&apos;s own traces, annotations, models,
        and runs. If you run your own Stash, set <Code>STASH_URL</Code> to your backend instead.
      </P>
      <CodeBlock lang="bash">{`export STASH_URL=https://api.joinstash.ai
export STASH_API_KEY="<your key>"

curl -s "$STASH_URL/api/v1/rm/formats" ${AUTH}`}</CodeBlock>
      <P>Examples on this page use those two variables. Request and response bodies are JSON unless noted.</P>

      <P>
        Reward-model APIs require an account enrolled in the experiment. Accounts that existed at
        rollout remain disabled and receive 404 from every endpoint here. New accounts are enabled
        by default; eligibility is per account, including new accounts in existing organizations.
      </P>

      <H3>Errors</H3>
      <P>
        Errors return <Code>{`{"detail": "…"}`}</Code>. An id that belongs to another user is a{" "}
        <Code>404</Code>, the same as one that doesn&apos;t exist. A request Stash can&apos;t act on,
        such as an unparseable import, a rating on a system step, or a rejected SQL query, is a{" "}
        <Code>422</Code> whose <Code>detail</Code> says why.
      </P>

      <Table
        head={["method", "path", "summary"]}
        rows={[
          ["GET", <span key="p" className="font-mono">{"/formats"}</span>, "List import formats"],
          ["POST", <span key="p" className="font-mono">{"/traces/import"}</span>, "Import traces"],
          ["GET", <span key="p" className="font-mono">{"/traces"}</span>, "List traces"],
          ["GET", <span key="p" className="font-mono">{"/traces/{trace_id}"}</span>, "Get a trace with steps, annotations, scores"],
          ["DELETE", <span key="p" className="font-mono">{"/traces/{trace_id}"}</span>, "Delete a trace"],
          ["POST", <span key="p" className="font-mono">{"/traces/{trace_id}/annotations"}</span>, "Annotate a trace or step"],
          ["PATCH", <span key="p" className="font-mono">{"/annotations/{annotation_id}"}</span>, "Update an annotation or flag a label error"],
          ["DELETE", <span key="p" className="font-mono">{"/annotations/{annotation_id}"}</span>, "Delete an annotation"],
          ["GET", <span key="p" className="font-mono">{"/export/traces"}</span>, "Export traces as JSONL"],
          ["GET", <span key="p" className="font-mono">{"/export/annotations"}</span>, "Export annotations as JSONL"],
          ["GET", <span key="p" className="font-mono">{"/export/pairs"}</span>, "Export training pairs as JSONL"],
          ["POST", <span key="p" className="font-mono">{"/reward-models"}</span>, "Train a reward model"],
          ["GET", <span key="p" className="font-mono">{"/reward-models"}</span>, "List reward models"],
          ["GET", <span key="p" className="font-mono">{"/reward-models/{id}"}</span>, "Get a reward model"],
          ["GET", <span key="p" className="font-mono">{"/reward-models/{id}/weights"}</span>, "Download the trained weights"],
          ["POST", <span key="p" className="font-mono">{"/gepa-runs"}</span>, "Start a GEPA run"],
          ["GET", <span key="p" className="font-mono">{"/gepa-runs"}</span>, "List GEPA runs"],
          ["GET", <span key="p" className="font-mono">{"/gepa-runs/{id}"}</span>, "Get a GEPA run"],
          ["GET", <span key="p" className="font-mono">{"/gepa-runs/{id}/skill"}</span>, "Download the best skill as SKILL.md"],
          ["POST", <span key="p" className="font-mono">{"/query"}</span>, "Run read-only SQL"],
        ]}
      />

      <H2>Formats</H2>
      <Endpoint method="GET" path="/formats">List the import formats this server accepts.</Endpoint>
      <CodeBlock lang="json">{`[{"name": "stash", "description": "…"}, {"name": "openai_chat", "description": "…"}, …]`}</CodeBlock>

      <H2>Traces</H2>
      <Endpoint method="POST" path="/traces/import">Import one payload of traces.</Endpoint>
      <ParamTable
        params={[
          { name: "format", type: "string", desc: "A format name from /formats, or auto.", required: true },
          { name: "data", type: "string", desc: "The file contents, as one string.", required: true },
        ]}
      />
      <CodeTabs
        tabs={[
          {
            label: "curl",
            lang: "bash",
            code: `jq -Rs '{format: "auto", data: .}' traces.jsonl \\
  | curl -s "$STASH_URL/api/v1/rm/traces/import" \\
      -H "Authorization: Bearer $STASH_API_KEY" \\
      -H "Content-Type: application/json" \\
      --data @-`,
          },
          {
            label: "Python",
            lang: "python",
            code: `requests.post(
    f"{STASH_URL}/api/v1/rm/traces/import",
    headers={"Authorization": f"Bearer {STASH_API_KEY}"},
    json={"format": "auto", "data": open("traces.jsonl").read()},
)`,
          },
        ]}
      />
      <CodeBlock lang="json">{`{"format": "openai_chat", "imported": 128, "trace_ids": ["…", …]}`}</CodeBlock>
      <P>
        <Code>format</Code> in the response is the format that was used, which tells you what{" "}
        <Code>auto</Code> detected. The import is all or nothing: any error is a <Code>422</Code> and
        stores no traces. That includes <Code>auto</Code> matching no format, a payload that doesn&apos;t
        parse as its format, a trace with only system steps, and a trace with no title and no user
        step. Re-importing a trace with the same <Code>id</Code> replaces its steps and deletes the
        annotations on them. See{" "}
        <a href="/docs/trace-format" className="text-brand hover:underline">Trace format</a>.
      </P>

      <Endpoint method="GET" path="/traces">List traces, paginated.</Endpoint>
      <ParamTable
        params={[
          { name: "limit", type: "integer", desc: "Page size, 1 to 500. Default 50." },
          { name: "offset", type: "integer", desc: "Rows to skip. Default 0." },
        ]}
      />
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/traces?limit=50&offset=0" ${AUTH}`}</CodeBlock>
      <P>Returns <Code>{`{"traces": [TraceSummary], "total": int}`}</Code>, newest first.</P>

      <Endpoint method="GET" path="/traces/{trace_id}">A trace with its steps, annotations, and reward model scores.</Endpoint>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/traces/<trace_id>" ${AUTH}`}</CodeBlock>
      <P>Returns a <Code>TraceDetail</Code>. Step ids for annotating come from this response.</P>

      <Endpoint method="DELETE" path="/traces/{trace_id}">Delete a trace and its annotations. Returns 204.</Endpoint>
      <CodeBlock lang="bash">{`curl -s -X DELETE "$STASH_URL/api/v1/rm/traces/<trace_id>" ${AUTH}`}</CodeBlock>

      <H2>Annotations</H2>
      <Endpoint method="POST" path="/traces/{trace_id}/annotations">Annotate a whole trace, or one step.</Endpoint>
      <ParamTable
        params={[
          { name: "step_id", type: "string", desc: "A step of this trace. Omit to annotate the whole trace." },
          { name: "rating", type: "1 | -1", desc: "+ or −. Not allowed on a system step." },
          { name: "comment", type: "string", desc: "Free text. An annotation needs a rating, a comment, or both." },
          { name: "quote", type: "object", desc: "{text, prefix, suffix}: the highlighted span. Requires step_id, and text must appear in the step's content." },
        ]}
      />
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/traces/<trace_id>/annotations" \\
  ${JSON_HEADERS} \\
  -d '{"step_id": "<step_id>", "rating": -1, "comment": "Skipped the policy check"}'`}</CodeBlock>
      <P>Returns the <Code>Annotation</Code>. Breaking any rule in the table is a <Code>422</Code>.</P>

      <Endpoint method="PATCH" path="/annotations/{annotation_id}">Change a rating or comment, or flag a label error.</Endpoint>
      <P>Only the fields you send change. The step and quote are fixed once created.</P>
      <ParamTable
        params={[
          { name: "rating", type: "1 | -1 | null", desc: "New rating." },
          { name: "comment", type: "string | null", desc: "New comment." },
          { name: "label_error", type: "boolean", desc: "true excludes the annotation from training and GEPA." },
          { name: "label_error_note", type: "string", desc: "Why the label is wrong." },
        ]}
      />
      <CodeBlock lang="bash">{`curl -s -X PATCH "$STASH_URL/api/v1/rm/annotations/<annotation_id>" \\
  ${JSON_HEADERS} \\
  -d '{"label_error": true, "label_error_note": "Refund was within policy"}'`}</CodeBlock>

      <Endpoint method="DELETE" path="/annotations/{annotation_id}">Delete an annotation. Returns 204.</Endpoint>
      <CodeBlock lang="bash">{`curl -s -X DELETE "$STASH_URL/api/v1/rm/annotations/<annotation_id>" ${AUTH}`}</CodeBlock>

      <H2>Export</H2>
      <P>
        All three return JSONL (<Code>application/x-ndjson</Code>), one object per line, for
        everything you own.
      </P>
      <Endpoint method="GET" path="/export/traces">Traces in the Stash Trace Format. Re-importable as-is.</Endpoint>
      <Endpoint method="GET" path="/export/annotations">
        One annotation per line; fields in <a href="/docs/annotations#exporting-annotations" className="text-brand hover:underline">Annotations</a>.
      </Endpoint>
      <Endpoint method="GET" path="/export/pairs">
        The training pairs your current labels produce, capped at 4000:{" "}
        <Code>{`{"chosen": str, "rejected": str}`}</Code>.
      </Endpoint>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/export/traces"      ${AUTH} > traces.jsonl
curl -s "$STASH_URL/api/v1/rm/export/annotations" ${AUTH} > annotations.jsonl
curl -s "$STASH_URL/api/v1/rm/export/pairs"       ${AUTH} > pairs.jsonl`}</CodeBlock>

      <P>
        The pairs export contains pairs built from explicit API ratings. It does not run feedback
        extraction or export a model&apos;s saved feedback-derived training evidence.
      </P>

      <H2>Reward models</H2>
      <Endpoint method="POST" path="/reward-models">Queue a training job.</Endpoint>
      <ParamTable
        params={[
          { name: "name", type: "string", desc: "Display name.", required: true },
          { name: "trace_ids", type: "string[]", desc: "At least one trace UUID owned by you. Only these traces supply training pairs.", required: true },
          { name: "base_model", type: "string", desc: "Hugging Face model id. Default Qwen/Qwen3-0.6B." },
          { name: "epochs", type: "integer", desc: "Training epochs. Default 1." },
          { name: "max_pairs", type: "integer", desc: "Cap on training pairs. Default 4000." },
        ]}
      />
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/reward-models" \\
  ${JSON_HEADERS} \\
  -d '{"name": "refund-policy", "trace_ids": ["<trace_id>"]}'`}</CodeBlock>
      <P>
        Returns a <Code>RewardModel</Code> with status <Code>queued</Code>. Feedback extraction and
        the minimum of two usable pairs are checked in the worker. The deployment sets{" "}
        <Code>RM_COMPUTE</Code>; sending <Code>compute</Code> or any unknown request field returns 422.
        An unowned trace ID returns 404.
      </P>

      <Endpoint method="GET" path="/reward-models">List your reward models, newest first.</Endpoint>
      <Endpoint method="GET" path="/reward-models/{id}">Get one reward model. Poll this for status and metrics.</Endpoint>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/reward-models/<id>" ${AUTH}`}</CodeBlock>
      <Endpoint method="GET" path="/reward-models/{id}/weights">Get a private checkpoint download URL.</Endpoint>
      <P>
        Returns <Code>{`{"url": "https://…"}`}</Code> after checking ownership and succeeded status;
        otherwise 404. The URL expires after five minutes. Download from that URL without forwarding
        your Stash API key. The gzip archive contains a <Code>reward-model/</Code> directory with
        model weights, tokenizer files, and <Code>reward_stats.json</Code>.
      </P>
      <CodeBlock lang="bash">{`set -euo pipefail
reward_weights_url="$(curl -fsS "$STASH_URL/api/v1/rm/reward-models/<id>/weights" ${AUTH} | jq -er '.url')"
curl -fL "$reward_weights_url" --output reward-model.tar.gz
tar xzf reward-model.tar.gz`}</CodeBlock>

      <H2>GEPA runs</H2>
      <Endpoint method="POST" path="/gepa-runs">Queue a GEPA run that writes a skill.</Endpoint>
      <ParamTable
        params={[
          { name: "reward_model_id", type: "string", desc: "One of your reward models with status succeeded, used as the metric. Another user's is a 404; an unfinished one is a 422.", required: true },
          { name: "task_model", type: "string", desc: "LiteLLM task model. Default anthropic/claude-haiku-4-5." },
          { name: "task_api_base", type: "string", desc: "OpenAI-compatible base URL (vLLM, SGLang, …) for the task model." },
          { name: "reflection_model", type: "string", desc: "Model that writes skill bodies. Default anthropic/claude-sonnet-5." },
          { name: "max_metric_calls", type: "integer", desc: "Budget of example evaluations. Default 40." },
        ]}
      />
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/gepa-runs" \\
  ${JSON_HEADERS} \\
  -d '{
    "reward_model_id": "<reward_model_id>",
    "task_model": "openai/Qwen/Qwen3-8B",
    "task_api_base": "http://gpu-box.internal:8000/v1",
    "reflection_model": "anthropic/claude-sonnet-5"
  }'`}</CodeBlock>
      <P>Returns a <Code>GepaRun</Code> with status <Code>queued</Code>. Only <Code>reward_model_id</Code> is required. The worker generates the skill name and description; they are null until success.</P>

      <Endpoint method="GET" path="/gepa-runs">List your GEPA runs, newest first.</Endpoint>
      <Endpoint method="GET" path="/gepa-runs/{id}">Get one run, including its result once it succeeds.</Endpoint>
      <Endpoint method="GET" path="/gepa-runs/{id}/skill">The best skill as a text/markdown attachment named SKILL.md.</Endpoint>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/gepa-runs/<id>/skill" ${AUTH} -o SKILL.md`}</CodeBlock>
      <P>A <Code>404</Code> until the run has succeeded.</P>

      <H2>SQL query</H2>
      <Endpoint method="POST" path="/query">Run one read-only SELECT over your data.</Endpoint>
      <P>
        Each request gets a fresh in-memory DuckDB holding only your rows. Send exactly one{" "}
        <Code>SELECT</Code> (or <Code>WITH … SELECT</Code>), checked with DuckDB&apos;s own parser.
        File and network access are disabled. Results are capped at 1000 rows, and{" "}
        <Code>truncated</Code> is true when there were more. A query that runs longer than 10 seconds
        is stopped with a <Code>422</Code>, <Code>query exceeded 10s</Code>; DuckDB errors come back as
        a <Code>422</Code> with DuckDB&apos;s message.
      </P>
      <CodeTabs
        tabs={[
          {
            label: "curl",
            lang: "bash",
            code: `curl -s "$STASH_URL/api/v1/rm/query" \\
  ${JSON_HEADERS} \\
  -d '{"sql": "SELECT source_format, count(*) AS n FROM traces GROUP BY 1"}'`,
          },
          {
            label: "Python",
            lang: "python",
            code: `body = requests.post(
    f"{STASH_URL}/api/v1/rm/query",
    headers={"Authorization": f"Bearer {STASH_API_KEY}"},
    json={"sql": "SELECT source_format, count(*) AS n FROM traces GROUP BY 1"},
).json()
rows = [dict(zip(body["columns"], row)) for row in body["rows"]]`,
          },
        ]}
      />
      <CodeBlock lang="json">{`{"columns": ["source_format", "n"],
 "rows": [["openai_chat", 128], ["otel", 40]],
 "truncated": false}`}</CodeBlock>

      <H3>Tables</H3>
      <Table
        head={["table", "columns"]}
        rows={[
          ["traces", "id, external_id, title, source_format, metadata (JSON), created_at"],
          ["steps", "id, trace_id, idx, role, content, tool_name, tool_input (JSON), tool_call_id, metadata (JSON)"],
          ["annotations", "id, trace_id, step_id, step_index, rating, comment, quote (JSON), label_error, label_error_note, created_at"],
          ["scores", "reward_model_id, reward_model_name, trace_id, score, created_at"],
        ]}
      />
      <P>
        <Code>SELECT * FROM steps LIMIT 0</Code> returns a table&apos;s column names without any rows.
      </P>

      <H3>Example: negative rate per tool</H3>
      <P>Which tools are your reviewers rating down most often?</P>
      <CodeBlock lang="sql">{NEGATIVE_RATE_SQL}</CodeBlock>

      <H3>Example: worst-scored traces nobody has reviewed</H3>
      <CodeBlock lang="sql">{`SELECT t.title, sc.score
FROM scores sc
JOIN traces t ON t.id = sc.trace_id
WHERE sc.reward_model_name = 'refund-policy'
  AND t.id NOT IN (SELECT trace_id FROM annotations)
ORDER BY sc.score ASC
LIMIT 20`}</CodeBlock>

      <H3>Example: where reviewers disagree</H3>
      <CodeBlock lang="sql">{`SELECT trace_id, step_index,
       count(*) FILTER (WHERE rating = 1)  AS plus,
       count(*) FILTER (WHERE rating = -1) AS minus
FROM annotations
WHERE NOT label_error
GROUP BY trace_id, step_index
HAVING plus > 0 AND minus > 0`}</CodeBlock>
      <Callout>
        To send multi-line SQL with curl, save it to a file and build the body with{" "}
        <Code>{`jq -Rs '{sql: .}' query.sql`}</Code>.
      </Callout>

      <H2>Objects</H2>
      <H3>TraceSummary</H3>
      <ParamTable
        params={[
          { name: "id", type: "string", desc: "Stash's trace id." },
          { name: "external_id", type: "string | null", desc: "The id you imported it with." },
          { name: "title", type: "string", desc: "Title, or the first 80 characters of the first user step." },
          { name: "source_format", type: "string", desc: "The format it was imported from." },
          { name: "step_count", type: "integer", desc: "Number of steps." },
          { name: "positive_count", type: "integer", desc: "+ ratings on the trace and its steps, not counting flagged ones. API-rating counts only; feedback-derived pairs are not counted here." },
          { name: "negative_count", type: "integer", desc: "− ratings on the trace and its steps, not counting flagged ones." },
          { name: "comment_count", type: "integer", desc: "Annotations with a comment." },
          { name: "label_error_count", type: "integer", desc: "Annotations flagged as label errors." },
          { name: "latest_score", type: "object | null", desc: "{reward_model_id, reward_model_name, score} from the most recently finished reward model that scored this trace." },
          { name: "created_at", type: "string", desc: "ISO 8601." },
        ]}
      />

      <H3>TraceDetail</H3>
      <P>Every <Code>TraceSummary</Code> field, plus:</P>
      <ParamTable
        params={[
          { name: "metadata", type: "object", desc: "The trace's metadata." },
          { name: "steps", type: "[Step]", desc: "In order." },
          { name: "annotations", type: "[Annotation]", desc: "Oldest first." },
          { name: "scores", type: "array", desc: "[{reward_model_id, reward_model_name, score, created_at}], one per reward model that scored this trace, most recent model first." },
        ]}
      />

      <H3>Step</H3>
      <ParamTable
        params={[
          { name: "id", type: "string", desc: "Step id. Use it as step_id when annotating." },
          { name: "index", type: "integer", desc: "Position in the trace, from 0." },
          { name: "role", type: "string", desc: "system, user, assistant, or tool." },
          { name: "content", type: "string", desc: "The step's text." },
          { name: "tool_name", type: "string | null", desc: "Tool called, or that produced this result." },
          { name: "tool_input", type: "object | null", desc: "Tool call arguments." },
          { name: "tool_call_id", type: "string | null", desc: "Links a call and its result." },
          { name: "metadata", type: "object | null", desc: "Per-step metadata." },
        ]}
      />

      <H3>Annotation</H3>
      <ParamTable
        params={[
          { name: "id", type: "string", desc: "Annotation id." },
          { name: "trace_id", type: "string", desc: "The trace it belongs to." },
          { name: "step_id", type: "string | null", desc: "The step, or null for the whole trace." },
          { name: "rating", type: "1 | -1 | null", desc: "+, −, or none." },
          { name: "comment", type: "string | null", desc: "Free text." },
          { name: "quote", type: "object | null", desc: "{text, prefix, suffix}." },
          { name: "label_error", type: "boolean", desc: "Flagged as wrong; excluded from training and GEPA." },
          { name: "label_error_note", type: "string | null", desc: "Why it was flagged." },
          { name: "author_id", type: "string", desc: "User who wrote it." },
          { name: "author_name", type: "string", desc: "That user's name." },
          { name: "created_at", type: "string", desc: "ISO 8601." },
        ]}
      />

      <H3>RewardModel</H3>
      <ParamTable
        params={[
          { name: "id", type: "string", desc: "Reward model id." },
          { name: "name", type: "string", desc: "Display name." },
          { name: "base_model", type: "string", desc: "Hugging Face model id it was trained from." },
          { name: "compute", type: "string", desc: "Deployment-selected runtime: local or modal. Read-only." },
          { name: "trace_count", type: "integer", desc: "Number of selected traces." },
          { name: "trace_ids", type: "string[]", desc: "Selected trace UUIDs; included by GET /reward-models/{id}." },
          { name: "epochs", type: "integer", desc: "Requested epochs." },
          { name: "max_pairs", type: "integer", desc: "Requested cap on pairs." },
          { name: "status", type: "string", desc: "queued, running, succeeded, or failed." },
          { name: "num_pairs", type: "integer | null", desc: "Usable pairs from selected traces, including feedback-derived pairs and the held-out split." },
          { name: "metrics", type: "object | null", desc: "train_pairs, eval_pairs, eval_accuracy, final_loss, epochs, device, seconds." },
          { name: "error", type: "string | null", desc: "Failure message when status is failed." },
          { name: "created_at", type: "string", desc: "ISO 8601." },
          { name: "started_at", type: "string | null", desc: "ISO 8601." },
          { name: "finished_at", type: "string | null", desc: "ISO 8601." },
        ]}
      />

      <H3>GepaRun</H3>
      <ParamTable
        params={[
          { name: "id", type: "string", desc: "Run id." },
          { name: "reward_model_id", type: "string", desc: "The reward model used as the metric." },
          { name: "skill_name", type: "string | null", desc: "Generated name; null until success." },
          { name: "skill_description", type: "string | null", desc: "Generated description; null until success." },
          { name: "task_model", type: "string", desc: "LiteLLM model string." },
          { name: "task_api_base", type: "string | null", desc: "OpenAI-compatible base URL, if set." },
          { name: "reflection_model", type: "string", desc: "LiteLLM model string." },
          { name: "max_metric_calls", type: "integer", desc: "Evaluation budget." },
          { name: "status", type: "string", desc: "queued, running, succeeded, or failed." },
          { name: "seed_skill", type: "string | null", desc: "The starting SKILL.md, with the description as its body." },
          { name: "seed_score", type: "number | null", desc: "The seed skill's mean score, for comparison." },
          { name: "best_skill", type: "string | null", desc: "The winning SKILL.md, frontmatter included." },
          { name: "best_score", type: "number | null", desc: "Its mean calibrated score over all examples, 0 to 1; 0.5 is the calibration mean of chosen/rejected texts." },
          { name: "candidates", type: "array | null", desc: "Every skill tried, as a full SKILL.md: [{skill, score}]." },
          { name: "error", type: "string | null", desc: "Failure message when status is failed." },
          { name: "created_at", type: "string", desc: "ISO 8601." },
          { name: "started_at", type: "string | null", desc: "ISO 8601." },
          { name: "finished_at", type: "string | null", desc: "ISO 8601." },
        ]}
      />
    </>
  );
}
