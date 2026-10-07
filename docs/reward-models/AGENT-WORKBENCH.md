# Agent Workbench: internal dogfood implementation

This implements the first three milestones of [the current specification](AGENT-WORKBENCH-SPEC.html): captured events receive JEV assessments; reviewed corrections produce separate grader and instruction drafts; released instructions are delivered to subsequent native coding sessions with inspectable receipts.

## Deploy and start using it

1. Apply database migrations through **0220** before deploying the new API and workers. Migrations 0217–0220 add workbench records, durable dispatch, instruction delivery, correction capture and human audit labels.
2. Configure **`TYPESAFE_API_KEY`** on the API and default Celery worker. `JEV_MODEL` defaults to `jev-1.13.0`; `JEV_TIMEOUT_SECONDS` defaults to 45. Configure the existing **`ANTHROPIC_API_KEY`** for correction extraction and draft generation. Never put either credential in the browser or a grader configuration.
3. Deploy the API, frontend, default Celery worker and Celery Beat together. Beat dispatches persisted work every 15 seconds. These jobs call hosted APIs; they do not train or run a model locally. Existing reward-model access (`users.reward_models_enabled`) controls access to the workbench.
4. Open **Traces → Graders**, create a grader, and set the repository to the exact working-directory path captured by the harness. Optionally restrict it to `codex` or `claude_code`. The initial grader processes already captured matching traces and then new events automatically. Pausing it stops new assessments. Creating a grader is the opt-in to sending its selected trace context to TypeSafe and correction context to the configured drafting provider.
5. Upgrade/reinstall the Stash CLI and native Codex or Claude Code plugin from this revision so SessionStart includes released workbench instructions. Existing plugins can continue uploading traces, but cannot receive the new instruction context until updated.
6. Do ordinary coding work. Open a trace's **Assessments** panel to inspect the target action, selected prefix, omissions, exact request, classification, probability data and raw response. Give Sam or Priyadarshan access using that trace's reviewer controls and their existing account email.
7. Use **Review** to accept, reject or correct interpretations; use audit samples to supply human verdicts without requesting changes. **Changes** shows the separate editable grader/instruction proposals and their checks. Accepted correction drafts are checked automatically by the dispatcher. Release remains explicit.
8. Release an instruction, start a **new** matching coding session, then open its delivery record. `offered` means the hook received the text. `captured` means its exact wrapper, version, text and hash were found in a model-visible native transcript event. Follow the link to inspect actual behavior separately.

## What each check establishes

- JEV classifies an assistant action or response against each configured criterion using recorded evidence available through that action. Later corrections are displayed alongside the result, never silently inserted into its original input. This is rubric evaluation, not causal credit assignment.
- JEV currently supplies choices and probabilities, not explanations or evidence citations. The inspector labels supplied context as context. Missing evidence and provider failure have different states.
- A grader comparison runs both configurations on exactly the same saved context. All requests are persisted before inference; outputs and partial failures are retained. It never executes the recorded agent's tool calls.
- The initial release gate requires at least five distinct traces/requests, at least one corrected error, and zero new errors on that set. The source trace, near-duplicate initial requests and identifiable explicit examples are excluded. Grouping is a lexical heuristic, not guaranteed semantic independence. Human labels are checked again at release, including whether a newer accepted label superseded them. Five examples are a small operational gate, not statistically established generalization.
- Without independent human labels, the check reports that quality cannot be measured and ordinary grader release is blocked. Review samples provide a way to collect those labels without manually assigning tasks to traces. An accepted requirement correction or an owner-created criteria edit can instead be activated with an explicit **accuracy unmeasured** acknowledgement. Previous labels do not validate it.
- Instruction checks validate text and the version being replaced. They **do not establish behavioral benefit**. Instructions are separate private workbench records injected through native SessionStart context; they are not published Skills and never enter generic draft skill synchronization. Unsupported harnesses have no instruction-delivery claim.
- Grader release and rollback record the last saved event in each trace and apply only to later events. Initial creation backfills existing records. Instruction release/rollback affects future eligible sessions; already assigned sessions retain their pinned version.

## Budgets, failure and access behavior

Automatic grading reserves at most 500 provider calls per grader per UTC day, with at most 12 new targets per pass. Multi-criterion results share one provider request. Original failed attempts remain inspectable when retried. Retry a failed trace from its assessment panel; daily budget exhaustion resumes on a later sweep after midnight UTC.

Correction extraction uses a conservative English-language prefilter, then a bounded model call: at most four calls per pass and 50 per owner per UTC day. This can miss corrections; direct comments and audit labels remain available. Extraction preserves source role, source event, exact quoted evidence and input; extracted proposals never silently become human-approved labels. Ordinary trace comments also prepare feedback when a matching grader is enabled.

The dispatcher repairs expired leases and retries broker dispatch. A provider failure is visible with retry controls. Check failures preserve partial reports. Repeated uploads do not duplicate successful grading or accepted correction extraction. Comparison checks are explicitly requested or triggered by accepted drafts; each considers at most 50 eligible labels. They are not included in the automatic-grading daily allowance.

A reviewer grant covers one trace and its feedback. It does not grant access to the owner's other traces, private grader examples, change contents, release controls or deletion. Native read-access recording keys can fetch already released instructions and create delivery bookkeeping; they cannot edit graders or release changes. Removing a grant removes future trace access.

## What is not implemented here

Milestone 4 remains separate: automatic release policies, randomized assignment to instruction versions, controlled prospective comparisons, and measured agent improvement. There is no claim that a higher score under a changed grader proves improved behavior. Automatic task execution, simulated tool environments, weight training, arbitrary cross-harness instruction delivery, and pairwise comparison mining are also outside this initial slice.

## Validation

The test suites exercise native transcript ingestion through real API/database calls with model and broker boundaries mocked, provider wire validation, exact input persistence, append/retry idempotence, future-event activation, team permissions, held-out comparison gates, correction capture budgets, and instruction delivery/rollback. Frontend interaction tests and headless screenshots cover the four workbench screens. A separate live TypeSafe call on synthetic test-reporting evidence succeeded with `jev-1.13.0`; no private trace or local model training was needed for that smoke test. End-to-end production deployment and a real new native session remain deployment acceptance steps.
