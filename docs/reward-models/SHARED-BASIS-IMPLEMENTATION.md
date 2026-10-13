# Shared reward basis: implemented experiment

This adds an experimental path from a saved shared checkpoint to private,
versioned customer heads, plus evidence collectors for adaptation, attacks and
actual agent execution. It does not replace the workbench's existing automatic
labeling/rule scores or establish the pitch's quality guarantees.

## What is implemented

The cloud `basis_train` job freezes a supported pretrained decoder critic and
learns a small residual feature basis from balanced source profiles. Feature 0
preserves the original critic's linear score, including its normalization offset.
The default head uses `[1, 0, ...]`. A separately configured population-residual
candidate can be trained, but it needs independent evidence before release.

Customer adaptation fits a regularized Bradley–Terry residual head on trusted
cached features. Zero labels retains the shared default. A label budget is an
experimental input, not a promised number sufficient for every workflow. Scores
and preference probabilities are not calibrated probabilities of task success.

Every feature/head pins the actual encoder bytes, basis parameters, input
contract and shared manifest. Heads include immutable source-label revisions.
Changed/revoked labels, changed linked traces and mismatched model versions
invalidate use. Shared pooled weights are available only to operator routes;
ordinary user tokens cannot download them, including the candidate's owner.

Private personalized scoring runs persist their own results. They do not update
global trace/action scores, consume the default scoring queue or appear as
default-model runs in the legacy trace UI.

## API workflow

Apply migrations `0237` then `0238` to a development deployment. Both the API
and reward Celery worker must include these modules; the feature task runs through
Modal and private artifact storage. No model inference or backbone training
belongs in the API process or on the laptop.

1. An operator creates a shared candidate using `POST /api/v1/admin/rm/candidates` with
   `evaluator_kind=shared_basis_v1`, an explicit reviewed base-model license,
   pinned revision and basis options. Training/release retain the existing
   operator corpus and release controls. Research guarantees remain false in
   release reports; synthetic tests cannot establish them.
   The basis default is a pinned Skywork scalar reward checkpoint, requiring
   explicit license review. Generic language-model weights with a newly initialized
   reward head are rejected by the training worker.
2. With a released experimental basis, its user creates
   `POST /api/v1/rm/customer-feature-jobs`: shared model ID, common task/context,
   two assistant alternatives and optionally an owned trace/version anchor.
   The worker computes both vectors from the saved checkpoint. Callers cannot
   submit vectors or declare their comparisons operator-verified.
3. Poll `GET /api/v1/rm/customer-feature-jobs/{id}` for the private original
   alternatives and resulting pair ID. Queued jobs survive broker failures.
   Explicit `/retry` permits fewer than three failed attempts and rejects stale
   trace/model pins.
4. Record an explicit choice using
   `POST /api/v1/rm/customer-heads/pairs/{pair_id}/label` with `winner=a|b`.
   Repeating the same label is idempotent. Revocation invalidates dependent heads.
5. Fit `POST /api/v1/rm/customer-heads/fit` with shared model ID, name, owned pair
   IDs and regularization. Head versions are immutable. `/compare` predicts on
   an owned cached pair using the default or an exact private head.
6. Existing trace scoring accepts `customer_head_id`. Retrieve persisted private
   results via `GET /api/v1/rm/customer-heads/scoring-runs/{run_id}`. Retrieval
   also checks current trace and source-label validity.

Owner-supplied context linked to a trace is not independently verified captured
evidence. Direct human preferences can personalize that owner's head; they do
not become gold outcome labels or shared-training permission.

There is no customer-head selector in the existing frontend in this change.
The experiment is exposed through the API and operator/cloud tools.

Migration rollback from `0238` removes personalized runs: the old schema cannot
represent them. Preserve those results before a rollback if they are needed.

## Evidence and claim boundaries

| Pitch capability | Implemented mechanism | Evidence still needed |
| --- | --- | --- |
| Useful pretrained start | Versioned pretrained critic plus Stash-trained residual basis | New owned outcomes on representative agent workflows |
| Learn customer preferences from 20–30 labels | Tiny private residual head and held-out learning curves | Unseen real customer/workflow curves against zero-label and challenger baselines |
| Resist reward hacking | Independent outcome oracle and bounded adaptive attack runner | Frozen attacks across representative tasks, attackers and query budgets; unrestricted immunity remains unsupported |
| Improve agents | Learned judge integrated into an isolated execution harness | Judge-selected changes and prospective paired/randomized real-workflow outcomes |

The first public development export scored 37/64 comparisons and discarded the
pretrained scalar prior. It is superseded by the anchor-preserving development
export: 512 fitting pairs, 128 evaluation comparisons, 98/128 correct. Its
default and pretrained anchor scores are identical: zero paired wins/losses.
The residual basis changed during training; the frozen 596,050,944-parameter
encoder was not optimized. These data establish a completed training/export
pilot, not a better Stash default.

A population-residual candidate fitted on the same 512/128 public development
split scored 95/128 (74.2%) against the anchor's 98/128 (76.6%), with 11 paired
wins and 14 losses. Its learned default weights were trained and saved, but this
trial regressed and was not promoted. Further source-only model selection and
fresh owned validation are required.

These pilots use human HelpSteer2 ratings (CC-BY-4.0) and the pinned Skywork
0.6B reward model (Apache-2.0). Rating criteria are source profiles, not customers.
Public-data foundation-training exposure is unknown. The later run uses the
model's official chat serialization. The earlier and later scores are not a
controlled improvement comparison because their data and serialization differ.
These official-chat artifacts are development models. Quality on the API's
Stash context renderer needs its own matching-contract benchmark before release.

The initial live harness run failed the artifact-format contract. It supplies no
agent-quality evidence. The corrected harness records generated source hashes,
actual isolated execution and independent strict checks, alongside learned
scores. Hidden expected answers and verifier labels are excluded from judge
input. A hand-authored candidate skill is not a reward-model-selected skill.

With real exported features on two owned synthetic exact-JSON workflows, the
40-test-task arithmetic score was 100% with zero or 20 labels. Inventory improved
from 22.5% at zero labels to mean 81.5% with 20 labels across five support samples;
30 labels reached 81.0%. This demonstrates a bounded adaptation experiment,
not a guarantee on real customers or a benefit from every additional label.

Fixed four-variant corruption campaigns compromised the default on 11/20 tasks:
an independently incorrect answer outranked the correct same-task baseline.
The preselected 20-label heads still failed 2/10 campaigns in each workflow.
These are synthetic stress tests with relative acceptance and fixed candidate
families, not a production false-accept rate or a general adaptive-attack bound.

The corrected live learned-reward harness passed 3/4 incumbent tasks and 4/4
hand-authored candidate tasks. Its mean learned score nevertheless favored the
incumbent (0.7406 versus 0.7312). On the sole invalid-versus-valid task the judge
preferred the valid candidate; pass/pass score differences reversed aggregate
selection. This probe verifies execution and learned scoring while exposing a
fitness/outcome disagreement. It does not establish reward-guided improvement.

Sanitized cloud evidence is recorded in `experiments/shared-basis-pilot.json`.
Artifacts remain private and are not promoted to the production default.

## Reproducing bounded experiments

`backend/scripts/prepare_basis_pilot.py` prepares public development jobs. It
downloads only public data and tokenizer files locally. Launch the resulting
job directory through `python -m rm_worker.modal_runner --job-dir ...` with
private storage/Modal credentials in the process environment. All substantive
feature extraction, basis training and reward inference occur in the cloud.

`basis_features` exports at most 500 pinned feature inputs per cloud job.
`backend/scripts/eval_reward_basis.py` fits/evaluates cached tiny heads and runs
configured attack endpoints. See `REWARD-BASIS-VALIDATION.md` for the strict
benchmark contract and statistical limits.

`harness` jobs may include `reward_model_key`: the learned normalized score then
drives the GEPA-compatible adapter, while independent execution checks remain
separate. Without a key, the optimization metric is explicitly an oracle
baseline. Generated Python executes only in separate cloud sandboxes with no
credentials, network access, mounts or expected outputs. Registered synthetic
utilities are infrastructure probes, not a customer-repository agent benchmark.

Local worker tests use tiny randomly initialized models and mocked cloud calls.
The CPU CI job disables Hugging Face downloads. Local tests do not run real
training, batch model inference or generated code.
