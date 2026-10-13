# Eval builder

Product decision from the [October 12 design review](https://notes.granola.ai/d/093efb83-b310-4694-8739-a0e159870f3c).

The main product has two areas: Traces for observability and Evals for creating, checking, and using decision models. Prompt optimization is deferred and removed from the main navigation. The old model-list URL opens Evals for current accounts; the legacy list remains at `/reward-models/models/legacy`, and explicitly pinned snapshots retain their view. Existing model detail URLs, APIs, and optimization records remain available; no production data is deleted.

## Workspace design

The eval list and detail workspace follow the compact toolbar, neutral surfaces, and table-oriented structure shown in [Braintrust’s playground UI](https://www.braintrust.dev/docs/evaluate/playgrounds). Instructions sit in a narrow configuration column; a single Save button in the page toolbar generates and applies the updated evaluator. One examples table shows outputs, labels, calibration/holdout/reference use, and feedback; opening a row expands a focused inspector directly beneath it for full content, corrections, and sandbox inspection. Add example and the API request example expand inline. A persistent Connect row shows this eval's full POST endpoint and offers a copy control; Connect is removed from the menu. There is no separate activation control or Draft/Active status in the workspace. These flows use no modal overlays. Held-out checks and generated criteria occupy separate panels in the main pane. Small sample checks carry a Limited data badge and show matched-label counts. Inline panels use a minus icon to collapse. Creation, testing, and usage share the same scoped visual styles, preserving the rest of the application and pinned product snapshots.

## Create and update

1. Name the eval and describe what good looks like. The creation page includes Back to evals above the form. Accept unstructured interview notes and explanations.
2. Use the single Examples collection and its inline Add example form to submit labeled good and bad outputs by pasting text or JSON, uploading files, or choosing recorded traces. The saved example appears in that same collection, where labels and feedback remain editable. Add reference material without labeling it. Trace annotations are imported separately as feedback, never included in the prediction input.
3. Automatically reserve a distinct labeled example for a held-out check while retaining at least two labels in calibration data. Show its input, human label, predicted label, and probability of the human label. Very small checks are presented as limited validation, not proof of generalization.
4. Save the eval with visible preparation, criteria generation, scoring, checking, and application progress. Show elapsed time, completion with a test action, or an actionable failure and retry. Progress counts completed stages, not an estimated time or fraction of provider computation. Hide previous scorecards while saving. Generate criteria with an LLM using only calibration examples and reference material. Show calibration examples as few-shot references to the judge. Fit a small classifier and calibrate probabilities; this does not fine-tune an LLM. Show the generated evaluation criteria by default. Validation shows the count of matched labels and tested examples rather than a percentage alone. This implements the core Jev + head approach in [Jevisify](https://docs.google.com/document/d/1WYWmdz8jtr3MvP6eikWtlmCbiRnjRlmoOfEXdWWeFsk/edit).
5. Save captures the latest instructions, generates criteria, scores the examples, fits the classifier, and applies the completed evaluator in one action. Failed saves keep the previous saved evaluator available and retain edits for retry. There is no user-facing staging or activation step. Quality measurements, including Limited data, stay visible; they do not require a separate approval before saving. The existing backend version and promotion APIs remain compatible, and successful Save uses their explicit force option to apply an otherwise valid fitted version even when a quality gate fails. Stale or missing heads still cannot be applied.

File inputs accept TXT, Markdown, JSON/JSONL, PDF, DOCX, PPTX, and common image formats up to 2 MB. Document parsing runs in a bounded subprocess. PDFs and decks use extracted text. Image outputs use a generated visual description, displayed alongside the original preview; the text judge evaluates that description. Upload screenshots to judge visual slide design. Inputs that cannot be read fail visibly.

For API file inputs, upload with `POST /api/v1/intuitions/inputs` (multipart `file`), then pass the returned item to `POST /api/v1/intuitions/{id}/predict` as `{"item": <returned item>, "caller": "my-agent"}`. Native image decoding follows the [Anthropic vision contract](https://platform.claude.com/docs/en/build-with-claude/vision); criterion decisions use the [TypeSafe evaluation API](https://docs.typesafe.ai/api).

## Use and review

- Open an eval from anywhere on its list row to visit its dedicated page. The page’s three-dot menu offers Download.
- Download a JSON snapshot of the saved model definition, active/draft calibration heads and frozen seeds, validation results, and examples. This is a definition export; inference still uses the configured judge provider.
- The visible Connect row displays this eval's POST endpoint and copy control. Request example expands an authenticated trace-shaped cURL request and MCP example inline. Calls to this endpoint are logged with input, output, caller, version, and timestamp and appear in Usage & corrections.
- Open in sandbox preloads a saved example directly into the editable sandbox input; Run eval explicitly scores it. Structured examples appear as JSON and retain their object input type when edited; invalid JSON disables the run until corrected. This inspects criterion answers and decisions, rather than providing independent evidence on examples used to build the eval. Test against any new output or recorded trace independently of eval creation.
- Sandbox and normal API calls use the same saved evaluator. Editing instructions does not silently switch either to a different test version. After Save succeeds, both use the updated version.
- Run a saved eval from the trace viewer and display its scorecard.
- Call the versioned prediction API for completed-run evals, proposed-action guardrails, or output verification in an agent loop. The existing API and MCP contracts are retained.
- Persist UI and API calls with input, output (or a provider failure), caller, timestamp, and eval version. Review and paginate the full call history. Human corrections become labeled calibration examples for subsequent updates.

## Boundaries

Whole-trace classification and per-criterion judge probabilities are distinct from action credit assignment. Existing action-credit numbers can remain visible in trace observability, but the eval builder does not claim that they establish causal responsibility or train an improved agent. No prompt optimization, RL, GPU training, or automatic customer-agent modifications are introduced by this product flow.

## Local preview

These screenshots use a separate local database and explicitly labeled demo data. The original support-reply scorecard uses previously recorded judge answers. Local preview provider calls are now enabled using server-side development credentials; the concise-answer demo was built with live rubric and judge calls. Data stays in the separate local database. No GPU or LLM fine-tuning runs locally.

![One Save action and visible Connect endpoint, with separate checks and criteria](assets/eval-save-preview.png)

![Sandbox with a selected example preloaded in the editable input](assets/eval-sandbox-preview.png)

![An endpoint call recorded in Usage & corrections](assets/eval-api-usage-preview.png)

![Creation form with Back to evals navigation](assets/eval-create-back-preview.png)
