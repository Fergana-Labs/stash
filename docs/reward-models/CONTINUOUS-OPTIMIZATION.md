# Continuous prompt optimization

The Optimization tab connects trace feedback, a personal reward model, prompt
experiments on future agent tasks, and business-outcome trends.

1. Capture or import traces. Review automatic Jev success/action credit and add
   corrections. Direct evaluation comments now also feed personal reward training;
   rejected feedback and comments on replaced actions are excluded.
2. Train a reward model from selected independent tasks. Choose **Begin prompt
   optimization** on the model, or train a model inside the Optimization form.
   Training is asynchronous; the optimization waits for the checkpoint.
3. Choose the agent, exact workload/project scope, initial supplementary
   instructions, and a numeric business metric with direction, range and allowed
   regression. Starting enables generation, remote scoring and automatic promotion
   for the configured number of rounds.
4. Connect `stash-mcp` and copy the agent instructions from the dashboard. Every
   new task calls `stash_optimization_start_run` with a stable unique work key and
   actual agent version. Preserve its exact returned wrapper in the recorded
   context. Existing system instructions and permissions remain authoritative.
5. Native uploads can complete automatically: pass `session_id` when starting the
   run. Other runners import the real trace with external ID equal to `work_key`,
   or call `stash_optimization_finish_run` after the final response is captured.
6. Report the actual business measurement with `stash_optimization_record_outcome`
   or the dashboard's **Record outcome** form. Keep the source record/reference.
   Delayed outcomes are supported. Missing measurements never become zero or a
   success label. Outcomes are immutable and retries are idempotent.

The dashboard shows daily reward and business means separately for each prompt
version, coverage counts, exact instructions, comparison reports, run evidence,
and release history. Pause stops new assignments and new compute dispatch;
already running jobs can finish. Rollback selects an original/previously promoted
prompt, cancels the pending comparison, and pauses. Resume to use that selection
on new tasks. Existing tasks retain their assignments.

## Online loop

An LLM proposes one focused instruction change from training feedback and recent
real runs. Each round randomly assigns a fixed number of new tasks to the current
and candidate prompts. Assignments are idempotent and bounded per arm. The agent
version must stay fixed during the comparison. Extra tasks use the current prompt
while the cohort finishes. Future rounds use the latest promoted prompt.

The pinned personal reward checkpoint scores up to 64 evenly distributed actions
after the assignment; the mean normalized action credit is the run's reward.
Candidate instructions and optimization MCP bookkeeping are withheld from the
scorer. Original instructions and task context remain available within the
checkpoint's context budget. Evidence and score inputs are frozen on submission,
so later edits or transcript growth cannot rewrite history.

Promotion requires the entire cohort to finish, every business outcome to arrive,
an approximate 99% reward-difference interval above zero, and a business-difference
interval within the configured regression allowance. These intervals use sample
variance and a normal approximation; small samples and changing workloads limit
their reliability. They are prototype decision gates, not a guarantee of causal
or general improvement. Abandoned tasks remain visible and prevent promotion of
that cohort. Reward-model training/evaluation traces are excluded from online
comparisons. Business values are authenticated customer reports, not independently
verified analytics or inferred customer satisfaction.

The optimizer changes supplementary prompts, not agent or Jev weights. It keeps
one reward-model version per optimization so the trend's scale stays fixed. Start
a new optimization when changing the reward model or underlying agent version.
After the configured round limit, the current prompt remains available and
submitted runs can still be scored; pause to stop new assignments/dispatch.

## Deployment

Apply migration **0224** and deploy frontend, API, default/reward workers, Celery
Beat and the CLI together. Existing reward-model/checkpoint account gates apply.
Configure Anthropic for candidate generation and the existing Modal/private-S3
reward worker for scoring. Scoring always invokes `rm_worker.modal_runner`; it
never loads model weights on the API host or developer laptop.

Beat reconciles every 30 seconds. Jobs have durable rows, claims and expiring
leases, broker redispatch, and a maximum of three attempts. Exhausted failures
appear in the dashboard; Resume explicitly retries failed work. A missing native
trace or incomplete final response remains visible as pending capture.

REST endpoints are under `/api/v1/rm/optimizations`: create/list, `/{id}`,
`/{id}/control`, `/{id}/runs`, and `/runs/{id}/{trace,outcome,abandon}`. The owner-only
`GET /runs/{id}` returns the immutable trace, scoring inputs and scores. MCP also
exposes trace import/read, annotation and personal reward training.

This prototype adds no replay executor for arbitrary customer tools. Actual agent
execution stays in the connected harness; production measurement requires that
harness and the business system to provide their real traces and outcomes.
