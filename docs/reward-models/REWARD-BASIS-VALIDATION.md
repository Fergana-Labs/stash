# Reward-basis benchmark runner

This runner measures cached learned features and executes configured adaptive
attack endpoints. It does not train the backbone, download a model, establish a
production checkpoint, or infer agent improvement from evaluator scores.

## Cached-feature learning curves

Use the contract in `reward-basis-benchmark.schema.json`. Export the *same*
normalized features used by serving. Copy `feature_version`, `manifest_digest`,
`basis_dimension`, `global_head.weights` (as `global_weights`) and
`training_lineage` from the shared model manifest. Attach those feature pins to
every attempt. Hash the serialized task/attempt/evidence input as
`content_sha256`, retaining the authoritative source snapshot separately.

Give every comparison a stable task group, customer, workflow and partition:
`train`/`dev` for source evidence, `support` for adaptation, and `test` for final
measurement. Target customers *and* workflow IDs must be absent from source
training/development and the model's declared training lineage. Related
attempts and revisions cannot cross partitions. IDs alone do not establish
semantic task independence; dataset owners must assign meaningful groups.
The validator checks declared shared training exposure, not unknown foundation
pretraining. Shared-manifest labels and features are not an independent oracle.

Labels are `a`, `b`, `tie`, or `insufficient_evidence`, with an independent human
or executable-oracle reference and an explicit `synthetic` flag. Only binary
comparisons count toward head adaptation. Ties and insufficient evidence are
excluded from binary accuracy and reported separately. Repeating one identical
comparison under new IDs cannot inflate the adaptation label budget.

```sh
python -m backend.scripts.eval_reward_basis \
  --dataset benchmark.json --output validation-report.json --repeats 5 --seed 42
```

The output contains 0/5/10/20/30/50/100-label curves for each held-out target,
with nested randomly sampled support sets per repetition. Inadequate budgets
are reported as `insufficient_support`, never padded by resampling duplicates.
Each repetition records support IDs, the actual fitted head and its digest.
Reported preference log loss, Brier score, calibration bins and risk/coverage
are descriptive metrics. Bradley–Terry estimates are not certified confidence
or probabilities of task success. Repetitions reuse the same test population;
they are not additional independent test tasks or confirmatory confidence bounds.

The checked-in `rm_worker/tests/fixtures/reward_basis_benchmark.json` contains
owned synthetic arithmetic/inventory cases with engineered features. Its
labels can be reproduced from artifact state. It tests contracts and fitting,
and always reports `synthetic_regression_only` evidence. It cannot pass a model
release gate or substantiate a customer adaptation guarantee.

## Adaptive attack endpoints

Pass `--attack-config attacks.json` to additionally run a configured protocol.
The configuration contains `protocol`, `tasks`, `generator_command`,
`evaluator_command`, `verifier_command`, and optional `timeout_seconds`.
Each command is a JSON array of executable arguments, invoked without a shell.
Use small invoker commands for cloud execution; do not configure substantial
model inference, training, or agent replay on the laptop.

`AttackProtocol` records the task distribution, attacker/evaluator/verifier
identities, exact shared-model and head versions, allowed modifications, score
access, per-task query budget and acceptance threshold. The model version in
customer-head release reports is the shared `manifest_digest`; the head version
is the canonical digest of the fitted head. Customer-specific campaigns also
record `customer_id` and `workflow_id`, which must match every task.

The generator receives:

```json
{"operation":"generate","task":{},"history":[],"query":0}
```

It returns a JSON candidate object. History includes prior candidates and score
feedback, with no verifier labels. A new task starts with empty history. The
evaluator and verifier receive `operation`, `task`, and `candidate`. Evaluator
responses require finite `score`, boolean `accepted`, `model_version`, and
`head_version`. Verifier responses require boolean `valid`, `independent: true`,
`verifier_id`, and `evidence_reference`, with optional finite `quality`.

The verifier must execute actual outcome checks outside agent-editable state.
It must not return the attacked evaluator's opinion as ground truth. Endpoint
identity and independence are recorded attestations, not a proof that endpoint
implementations are independent. Endpoints enforce allowed modifications and
tool permissions. Timeouts, unknown oracle outcomes and version drift make
campaigns incomplete; the runner withholds aggregate rates/bounds rather than
silently dropping unsuccessful jobs.

A campaign is compromised if any permitted candidate is accepted above the
threshold while independently invalid. Count task campaigns, not candidate
queries. A one-sided exact binomial upper bound is emitted only when all jobs
complete and the protocol declares independently representative campaigns and
freezing before final evaluation. Adaptive search *within* a campaign is allowed
by the frozen protocol. Cross-campaign adaptation, final-set tuning, correlated
tasks and uncorrected repeated peeking require different statistical treatment.
The bound covers the declared task population/attacker/budget, not arbitrary
adversaries. Synthetic attacks remain regression evidence even with intervals.

## Product gates and claims

The default report has `product_gate.status = not_assessed`. An explicit
`--policy policy.json` supplies `label_budget`, `min_test_task_groups`,
`min_accuracy`, `max_attack_upper` and `release_heads`, for example:

```json
{"label_budget":20,"min_test_task_groups":100,"min_accuracy":0.8,
 "max_attack_upper":0.05,
 "release_heads":[{"customer_id":"target-id","workflow_id":"workflow-id",
                   "head_version":"exact-fitted-head-digest"}]}
```

These numbers illustrate the policy shape, not validated or recommended
thresholds. Select heads before looking at final evidence. A release requires
performance and complete frozen attacks linked to the same selected head;
attacking another head on the same backbone is insufficient. The Python
`release_report` API accepts a list of attack reports for multiple targets.

Product threshold passes are separate from scientific claims. Reports explicitly
leave 20–30-label sample efficiency unsupported until grouped confirmatory
improvements versus zero-label and challenger baselines are supplied. Actual
agent improvement remains unsupported until independent paired agent execution
outcomes exist. Unrestricted reward-hacking guarantees remain unsupported.

## Pretrained anchor and development candidate comparisons

Shared training preserves supported decoder classifiers' pretrained scalar
head as feature 0. In normalized hidden coordinates, its projection is
`pretrained_weights * training_scale`, with a saved offset
`pretrained_weights · training_mean + pretrained_bias`. This reconstructs the
original linear score under the same serialization, to floating-point precision.
The remaining dimensions are a Stash-trained residual basis learned from source
profiles with regularization and an orthogonality penalty.

By default, global weights are `[1, 0, ...]`: immediate scores retain the public
pretrained critic, while customer heads can use the learned residual channels.
The manifest explicitly records `pretrained_anchor_only` and
`default_is_pretrained_anchor`. This does not substantiate a claim that Stash's
trained default quality weights improve on the pretrained critic.

`basis_options.fit_global_residual = true` creates a separate candidate whose
population residual is trained with shrinkage toward the pretrained prior.
Compare it against the anchor at equal input context/serialization and source
data. Reports include pretrained accuracy and paired wins/losses. Use the
model's official chat template for generic chat baseline comparisons; arbitrary
plain role labels are a different input distribution.

For the public HelpSteer pilot, select architecture and regularization using
source training/development groups. The 128/64 first pilot and subsequent
512/128 trial are development evidence. The public dataset may have been seen
by the foundation model, and human-rating criteria are source profiles rather
than real customers. Freeze the selected candidate before collecting new owned
task outcomes, unseen customer/workflow adaptation curves and adaptive attacks.
Neither a public benchmark score nor an anchor-preserving export establishes
real agent improvement or reward-hacking resistance.

Legacy artifacts without offsets use zero offsets and retain their v1 feature
extractor/hash semantics. New artifacts pin the offset file and v2 decoder
pooling semantics in their feature identity.
