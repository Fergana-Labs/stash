# Stash reward model training platform — design

Teams bring agent traces, annotate them the way they'd comment on a Google Doc
(highlight text, leave a comment, give it a + or −), and train a reward model
from those annotations, the same kind of reward model used in RLHF. A second
optimizer, GEPA, writes a skill for the agent (a SKILL.md it loads into its
context) using the written comments as feedback and the trained reward model
as the metric.

This is a separate product area inside the Stash monorepo. It does not read or
write the existing `sessions` / `history_events` tables; connecting the two is
later work.

## Components

```mermaid
flowchart LR
  subgraph Ingest
    F[Trace files<br/>OpenAI, Anthropic, OTel,<br/>Langfuse, LangSmith,<br/>Claude Code, Codex, Stash] --> A[Format adapters<br/>backend/services/rm/adapters]
  end
  A --> DB[(Postgres<br/>rm_* tables)]
  UI[Annotation UI<br/>frontend /reward-models] <--> API[REST API<br/>/api/v1/rm]
  API <--> DB
  API -->|enqueue| C[Celery heavy queue]
  C -->|job dir| W[rm_worker<br/>torch + transformers + gepa]
  W -->|local MPS/CUDA/CPU| W
  W -->|or| M[Modal GPU]
  W -->|result.json, scores.jsonl| C
  C --> DB
  API -->|/query| D[DuckDB over the<br/>caller's own rows]
```

| Piece | Location | Notes |
|---|---|---|
| Migration | `backend/migrations/versions/0208_reward_model_platform.py` | all `rm_*` tables |
| Adapters | `backend/services/rm/adapters.py` | every input format → canonical trace |
| Services | `backend/services/rm/*.py` | traces, annotations, datasets, jobs, query |
| Router | `backend/routers/reward_models.py` | prefix `/api/v1/rm` |
| Celery tasks | `backend/tasks/reward_models.py` | `heavy` queue; shells out to `rm_worker` |
| Worker | `rm_worker/` (top-level, own venv, own `requirements.txt`) | training, scoring, GEPA; never imported by the backend |
| UI | `frontend/src/app/(app)/reward-models/` | traces, annotation view, models, GEPA |
| Public docs | `www/app/docs/` (Stash Reward Models is the docs site) | overview, trace format, annotations, training, GEPA, API |

The backend never imports torch. It writes a job directory, runs the worker as
a subprocess with `RM_WORKER_PYTHON`, and reads the results back. Both
`RM_WORKER_PYTHON` and `RM_ARTIFACT_DIR` are required the moment a job runs;
a missing value raises with a message naming the variable.

## Canonical trace format (Stash Trace Format, JSONL)

One trace per line. This is the import format, the export format, and the
shape every adapter produces.

```json
{
  "id": "optional-external-id",
  "title": "Refund request for order 1182",
  "metadata": {"agent": "support-bot", "model": "qwen3-8b"},
  "steps": [
    {"role": "system",    "content": "You are a support agent..."},
    {"role": "user",      "content": "I want a refund for order 1182"},
    {"role": "assistant", "content": "", "tool_name": "lookup_order",
     "tool_input": {"order_id": "1182"}, "tool_call_id": "call_1"},
    {"role": "tool",      "content": "{\"status\": \"delivered\"}", "tool_name": "lookup_order",
     "tool_call_id": "call_1"},
    {"role": "assistant", "content": "Your order was delivered on..."}
  ]
}
```

- `role` ∈ `system | user | assistant | tool`. `content` is always a string.
- `tool_name`, `tool_input` (object), `tool_call_id`, `metadata` are optional per step.
- `id` is optional; when present, re-importing the same `id` for the same owner
  replaces the trace's steps (annotations on the old steps are deleted with them).
- `title` is optional; the default is the first 80 characters of the first user step.

### Supported input formats

`format` on import is one of the names below or `auto`. `auto` detects the
format from the payload's shape and fails with a 422 naming the formats it
tried when nothing matches.

| name | input | unit |
|---|---|---|
| `stash` | Stash Trace Format JSONL (above) | one trace per line |
| `openai_chat` | JSONL of `{"messages": [...]}` (fine-tuning format) or a JSON array of messages; handles `tool_calls` and `role: "tool"` | one trace per line |
| `anthropic_messages` | JSONL of `{"system": ..., "messages": [...]}`; content blocks `text`, `tool_use`, `tool_result`, `thinking` | one trace per line |
| `otel` | OTLP/JSON (`resourceSpans` and `resourceLogs`), single request or Collector file-exporter JSONL. Reads OTel GenAI semconv (`gen_ai.system_instructions`, `gen_ai.input.messages`, `gen_ai.output.messages`, the `gen_ai.client.inference.operation.details` event and the deprecated per-message log events), OpenInference (`llm.input_messages.*`, `llm.output_messages.*` incl. `message.contents`), and OpenLLMetry (`gen_ai.prompt.N.*`, `gen_ai.completion.N.*`). Built from LLM calls only; tool spans are not read because every tool call and result already appears in the next LLM call's messages. | one trace per `traceId` |
| `langfuse` | The `GET /api/public/traces/{traceId}` response (trace with `observations`), one object or a JSON array. Built from `GENERATION` observations. | one trace per trace |
| `langsmith` | LangSmith run export JSONL (runs with `trace_id`, `run_type`, `inputs`, `outputs`); built from `llm` runs ordered by `start_time` | one trace per `trace_id` |
| `claude_code` | Claude Code session transcript JSONL (`~/.claude/projects/**/*.jsonl`) | one trace per file |
| `codex` | Codex CLI rollout JSONL (`~/.codex/sessions/**/rollout-*.jsonl`) | one trace per file |

## Annotations

An annotation belongs to a trace and optionally to one step. It carries a
rating, a comment, or both.

| field | meaning |
|---|---|
| `step_id` | null = the whole trace; set = one step |
| `rating` | `1` (+), `-1` (−), or null |
| `comment` | free text, or null |
| `quote` | `{text, prefix, suffix}` — the highlighted span inside the step's content, anchored the same way page comments are (`page_comment_threads`). Requires `step_id`. |
| (system steps) | can carry comments (they feed GEPA) but not ratings: the reward model never sees system steps, so a rating there is a 422. A trace with only system steps fails import. |
| `label_error` | true = someone flagged this label as wrong. Flagged annotations are excluded from training and GEPA. |
| `label_error_note` | why it's wrong |

Annotation export (`GET /api/v1/rm/export/annotations`), one per line:

```json
{"trace_id": "…", "trace_external_id": "…", "step_index": 4, "rating": -1,
 "comment": "Promised a refund without checking the policy",
 "quote": {"text": "I've issued a full refund", "prefix": "Sure! ", "suffix": " to your card"},
 "label_error": false, "author": "henry", "created_at": "2026-09-29T03:12:00Z"}
```

## Reward model training

Training data is preference pairs built from the + and − ratings:

1. Drop annotations with `label_error = true`.
2. Collapse ratings per target (trace, or step): sum the ratings; positive sum
   → chosen, negative → rejected, zero → skipped.
3. Render each target to text. A trace renders all its non-system steps; a
   step renders the trace's non-system steps up to and including that step.
   The reward model never sees system steps: GEPA's skill is injected into
   the system message, so scoring it would let GEPA write the reward model's
   preferences into the skill instead of into the agent's behavior. Rendering is
   `"<role>: <content>"` per step joined with blank lines, with tool calls as
   `"assistant → <tool_name>(<tool_input json>)"`. An assistant step with both
   text and a tool call renders the text line, then the tool-call line.
4. Pairs = every (chosen, rejected) combination within the same granularity
   (trace with trace, step with step), shuffled with seed 0 and capped at
   `max_pairs` (default 4000).
5. Fewer than one chosen and one rejected target → the job fails with
   "need at least one + and one − label".

The model is `AutoModelForSequenceClassification(num_labels=1)` on the chosen
base model, trained with the Bradley–Terry loss
`-log σ(r(chosen) − r(rejected))`. A 10% held-out split (at least one pair)
reports pairwise accuracy. After training, the worker scores every trace the
owner has and the scores are stored in `rm_trace_scores`.

Default base model: `Qwen/Qwen3-0.6B`. Compute: `local` (MPS on Apple
silicon, CUDA when present, else CPU) or `modal` (A10G, same code). The
trained weights go to `RM_ARTIFACT_DIR/<reward_model_id>/model`.

### Job directory contract (backend ↔ worker)

```
<RM_ARTIFACT_DIR>/<job_id>/
  job.json          # written by backend: {"kind": "train"|"gepa", ...params}
  pairs.jsonl       # train: {"chosen": str, "rejected": str}
  score_items.jsonl # train: {"trace_id": str, "text": str}
  gepa_examples.jsonl # gepa: {"trace_id", "system": str|null, "messages": [{role, content}], "feedback": [str]}
  result.json       # written by worker
  scores.jsonl      # train, written by worker: {"trace_id": str, "score": float}
  model/            # train, written by worker
  worker.log
```

`result.json` for training: `{"metrics": {"train_pairs", "eval_pairs",
"eval_accuracy", "final_loss", "epochs", "device", "seconds"}}`. For GEPA:
`{"best_skill", "best_score", "seed_skill", "seed_score", "candidates": [{"skill", "score"}]}`
(each skill is the full rendered SKILL.md). GEPA job.json: `{"kind": "gepa",
"reward_model_dir", "skill_name", "skill_description", "task_model",
"task_api_base" (null when unset), "reflection_model", "max_metric_calls"}`.

Request defaults: `base_model` `Qwen/Qwen3-0.6B`, `epochs` 1, `max_pairs`
4000. A quote's `text` must occur in the step's content (422 otherwise).

## Skill creation (GEPA)

The output is a **skill for your agent**: a `SKILL.md` (YAML frontmatter with
`name` and `description`, then Markdown instructions) that the agent loads
into its context. The agent's own system prompt is never rewritten.

GEPA (Agrawal et al., 2025) evolves text by running it, reading textual
feedback on the results, and asking a reflection model to propose better
text, keeping a Pareto front of candidates. Here the text it evolves is the
skill's body:

- **Request** = `skill_name` (lowercase letters, digits, hyphens; 1–64
  chars) and `skill_description` (1–1024 chars; says when the agent should
  use the skill). Name and description are fixed for the run; GEPA only
  writes the body. The seed body is the description as a single line.
- **Examples** = traces with at least one non-flagged annotation. Each
  example carries the trace's own system prompt (`system`: the concatenated
  system steps, or null) and the input = the non-system steps before the
  first assistant step.
- **Candidate** = one text component, `skill_body`. The worker renders the
  full skill as
  `---\nname: <skill_name>\ndescription: <skill_description>\n---\n\n<skill_body>`.
- **Evaluation** = run `task_model` (any LiteLLM model string, including
  `openai/<name>` with `api_base` for vLLM/SGLang/any OpenAI-compatible
  server) with system message = the example's own system prompt (when
  present), a blank line, then
  `<skill name="<skill_name>">\n<rendered SKILL.md>\n</skill>`, followed by
  the example's input messages. The rendered conversation (reply included,
  system message excluded) is scored by the chosen trained reward model.
  GEPA's score is sigmoid((reward − mean) / std), where mean and std are the
  reward model's scores over the owner's traces at training time
  (`model/reward_stats.json`). Raw rewards saturate the sigmoid (a confident
  model scores a decent reply ~0.99) and leave GEPA no headroom.
- **Feedback** for reflection = the reward score plus every non-flagged
  comment annotators left on that trace. The reflection model is told it is
  writing the body of a SKILL.md for an agent and must return only the body.
- Traces with no input before their first assistant step are skipped; no
  examples left → the run fails. `max_metric_calls` defaults to 150. The
  reward model must be the caller's and `succeeded`.
- **Result** = the best skill (full rendered SKILL.md), its score, the seed
  skill and its score, and every candidate tried (full SKILL.md each).
  `GET /gepa-runs/{id}/skill` downloads the best one as `SKILL.md`.

## Querying

- REST for everything above.
- `POST /api/v1/rm/query {"sql": "..."}` runs read-only SQL in an in-memory
  DuckDB loaded with only the caller's rows, as tables `traces`, `steps`,
  `annotations`, `scores`. Exactly one SELECT statement (checked with DuckDB's
  own parser), external access disabled, results capped at 1000 rows, and a
  10-second limit.

## REST API (`/api/v1/rm`, bearer auth)

| method | path | body / query | returns |
|---|---|---|---|
| GET | `/formats` | | `[{name, description}]` |
| POST | `/traces/import` | `{format: str, data: str}` | `{format, imported, trace_ids}` |
| GET | `/traces` | `?limit=50&offset=0` | `{traces: [TraceSummary], total}` |
| GET | `/traces/{trace_id}` | | `TraceDetail` (steps + annotations + scores) |
| DELETE | `/traces/{trace_id}` | | 204 |
| POST | `/traces/{trace_id}/annotations` | `{step_id?, rating?, comment?, quote?}` | `Annotation` |
| PATCH | `/annotations/{annotation_id}` | `{rating?, comment?, label_error?, label_error_note?}` | `Annotation` |
| DELETE | `/annotations/{annotation_id}` | | 204 |
| GET | `/export/traces` | | JSONL (Stash Trace Format) |
| GET | `/export/annotations` | | JSONL |
| GET | `/export/pairs` | | JSONL `{chosen, rejected}` |
| POST | `/reward-models` | `{name, base_model, compute, epochs?, max_pairs?}` | `RewardModel` (status `queued`) |
| GET | `/reward-models` | | `[RewardModel]` |
| GET | `/reward-models/{id}` | | `RewardModel` |
| GET | `/reward-models/{id}/weights` | | `.tar.gz` of the trained model dir (weights, tokenizer, `reward_stats.json`), attachment `<name>-reward-model.tar.gz`; 404 until `succeeded` |
| POST | `/gepa-runs` | `{reward_model_id, skill_name, skill_description, task_model, task_api_base?, reflection_model, max_metric_calls?}` | `GepaRun` (status `queued`) |
| GET | `/gepa-runs` | | `[GepaRun]` |
| GET | `/gepa-runs/{id}` | | `GepaRun` |
| GET | `/gepa-runs/{id}/skill` | | best skill as `text/markdown` attachment `SKILL.md` (404 until succeeded) |
| POST | `/query` | `{sql}` | `{columns, rows, truncated}` |

`TraceSummary`: `{id, external_id, title, source_format, step_count,
positive_count, negative_count, comment_count, label_error_count, created_at,
latest_score: {reward_model_id, reward_model_name, score} | null}`.
`positive_count` / `negative_count` exclude label-error annotations, so they
count exactly what trains.

`TraceDetail`: TraceSummary fields + `metadata`, `steps: [Step]`,
`annotations: [Annotation]`, `scores: [{reward_model_id, reward_model_name,
score, created_at}]` (latest per model).

`Step`: `{id, index, role, content, tool_name, tool_input, tool_call_id, metadata}`.

`Annotation`: `{id, trace_id, step_id, rating, comment, quote, label_error,
label_error_note, author_id, author_name, created_at}`.

`RewardModel`: `{id, name, base_model, compute, status, num_pairs, metrics,
error, created_at, started_at, finished_at}`; status ∈ `queued | running |
succeeded | failed`. `GepaRun` has the same status field plus the GEPA result
fields.
