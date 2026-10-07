# Agent Workbench: automatic Jev evaluation

The workbench always asks Jev two questions: **was this recorded trace successful**, and **how much credit does each assistant action deserve**. There is no user-created grader, rubric, or manual task assignment in this flow. This supersedes the configurable-grader setup in the earlier HTML specification.

## Deployment and use

1. Apply migrations through **0221**, then deploy the API, frontend, default Celery worker and Celery Beat together. Migration 0221 queues existing captured traces for owners with `reward_models_enabled`. New or changed traces are queued by the existing database trigger. Beat dispatches work every 15 seconds.
2. Operators configure `TYPESAFE_API_KEY` on the API and worker; `JEV_MODEL` defaults to `jev-1.13.0` and `JEV_TIMEOUT_SECONDS` to 45. `ANTHROPIC_API_KEY` is used separately for correction extraction and draft generation. Keys never enter browser configuration. Accounts with reward-model access automatically send selected trace evidence to these services; creating a grader is no longer an opt-in or prerequisite.
3. Continue ordinary coding with the existing Stash trace uploader. Open **Traces**, then a trace's **Trace success & action credit** panel. A newly imported or changed trace needs no setup.
4. Inspect the recorded trace, each action's credit, the supplied evidence and omissions, the exact Jev request and response, and previous evaluations. A pending or failed evaluation is not an agent failure verdict.
5. Comment on an evaluation or action to record a correction against its saved trace version. **Review** holds interpretations for acceptance or rejection; **Changes** holds proposed agent instructions. Reviewer grants remain scoped to one trace. Evaluator corrections are retained as feedback; they do not rewrite the two fixed questions.
6. Instruction release remains explicit. The release scope is automatically derived from the captured harness and exact working directory. A capture without a working directory can be evaluated and its corrections interpreted and reviewed. Its interpretation explains why no automatically scoped instruction draft was created. Native Codex/Claude plugins receive released instructions in subsequent matching sessions. `offered` means the hook received them; `captured` means their exact wrapper, version, text and hash appeared in the native transcript. These receipts do not prove behavioral benefit.

## What Jev receives and returns

For trace success, the request includes user requests, applicable instructions, agent responses, tool calls and recorded results selected from one immutable trace version. The output is `success`, `partial_success`, `failure`, or `insufficient_evidence`, plus Jev's confidence and choice probabilities.

For action credit, the request identifies up to four specific assistant actions and includes both preceding context and subsequent results from that same saved version. Each action receives an ordinal estimate: −2 strongly negative, −1 negative, 0 neutral, +1 positive, +2 strongly positive, or insufficient evidence (no numeric value). Confidence is stored separately. Credits do not sum to 100%; they are retrospective model estimates, not experimentally identified causal contributions.

Example: a tool result says `FAILED test_zero`, then the agent says “all tests passed,” and a later user corrects that claim. The credit question for that claim can include the failed result and later correction. Jev's answer is a prediction to inspect or correct, not a guaranteed ground-truth label. Merely claiming success is insufficient evidence of success.

The worker waits while the latest recorded event is an unanswered user request, a tool call/result, or native commentary. It evaluates after a final assistant response. Native Codex `phase=final` and Claude `stop_reason=end_turn` identify completed responses; older/generic imports use a visibly labelled inferred response boundary. Neither means the entire session ended. If more work arrives, the current result becomes historical and a new trace version is evaluated after the next response.

Context is bounded: targets, the final response, first/latest user requests, matching tool results, recent instructions and remaining recent events receive priority. Some text can be clipped and events omitted. Every omission is saved, and Jev is instructed to return insufficient evidence when omitted context prevents a supported judgment. There are no fabricated citations or explanations: Jev returns choices and probabilities, while the UI exposes the evidence it was given.

## Persistence, retries and budgets

Every provider request is committed before inference. A saved evaluation fixes the event snapshot, fingerprint, policy version and model. Identical redeliveries reuse completed calls; later trace versions retain older inputs and outputs. One call evaluates trace success, then one call evaluates each batch of up to four actions. A trace with N actions therefore normally requires `1 + ceil(N / 4)` calls per recorded version.

Automatic Jev evaluation has **no daily call limit**. The worker processes at most **12 calls per pass**, then queues remaining evaluation work for another pass without waiting for a new day. Traces paused by the former daily cap resume automatically, reusing saved results. Transient provider failures retry up to three attempts per batch; failed requests remain inspectable. The owner can retry from the trace panel. Missing provider credentials are an explicit server error and automatically requeue after credentials become available. Expired worker leases cannot overwrite a replacement worker's results.

Migration backfill preserves running leases. The dispatcher also repairs completed queue rows lacking a current completed evaluation (including backfill consumed by old workers), and retries the specific stale database statement-plan error up to three worker attempts. Running work, waiting responses, hard provider errors and queued work are excluded from that repair; former Jev-cap deferrals are resumed separately. Previously failed, still-unreviewed corrections whose only error was missing repository scope are requeued for interpretation.

For deployment acceptance, compare evaluation coverage with queue status: a completed queue row alone does not establish that a Jev evaluation exists. Operators can requeue affected owned traces through `POST /api/v1/rm/workbench/traces/{trace_id}/assess`; completed provider batches are reused. Correction extraction's separate limits still apply.

Correction extraction retains its conservative English-language prefilter and limits: four calls per pass and 50 per owner per UTC day. It can miss corrections; direct comments remain available. Extracted proposals do not become approved labels. Instruction checks validate text and replacement version, not behavioral improvement. Existing historical rubric assessments and comparison APIs remain available for compatibility; the automatic worker uses only the fixed Jev policy.

## Validation and limits

Tests use native ingestion, API authorization, real PostgreSQL persistence and mocked provider responses. They cover automatic scheduling without a grader, retrospective evidence, version history, retry idempotence, evaluation beyond the former daily cap, recovery of paused traces, lost worker leases, trace sharing, corrections after event replacement, context limits and completion metadata. Frontend tests cover current/historical states, success versus execution errors, signed credit versus confidence, and feedback tied to an evaluation. These checks establish pipeline behavior; they do not establish Jev's judgment accuracy.

This change adds automatic evaluation. It does not train Jev, update agent weights, execute recorded tools, automatically release instructions, or establish measured improvement in future agent behavior. A production trace successfully evaluated with real Jev remains a deployment acceptance check.
