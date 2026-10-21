# Stash reward modelling research and validation plan

Research date: 12 October 2026. Proposed architecture and experiments, not achieved Stash model results.

Stash can make its architecture claim concrete by training a shared evaluator on agent work, deploying that checkpoint as the default, and adapting a small customer head over its frozen learned features. Start with a learned low-dimensional reward basis over a frozen open-weight backbone, followed by regularized customer weights. Add a shared trace adapter if held-out tests show that the frozen representation misses needed distinctions. Reward-hacking resistance, adaptation with 20–30 labels, and better agent outcomes require separate experiments. Neither a small head nor contrastive training guarantees these properties across arbitrary tasks.

The practical objective is one coherent system: **a pretrained Stash evaluator that works before customer training, improves with customer feedback, and is released only with evidence of quality under optimization.** Start with completed tasks and verified artifacts. Keep action-level diagnostic estimates separate from claims about causal credit.

## Claims and the evidence needed

| Intended claim | What must be built | Evidence needed before making the claim |
|---|---|---|
| We provide our own pretrained general evaluator | Open-weight foundation plus Stash-trained reward basis and default head, with a shared adapter if needed; hosted versioned inference | Checkpoint lineage, reproducible training manifest, successful inference for a new account, and held-out performance within stated workflows |
| Customers adapt it by training a lightweight head | Freeze shared parameters; fit only a few customer weights using trusted comparisons | Parameter-update audit, immutable shared checkpoint hash, head lineage and independent target-workflow evaluation |
| Around 20–30 labels are enough | A representation in which useful customer differences are low-dimensional | Learning curves on customers and workflow families absent from shared training, repeated support samples and a larger untouched test set |
| It resists reward hacking | Adaptive attack discovery, independent adjudication, repair training, and fresh attack evaluation | Attack success versus query budget, honest-task utility, exact attack conditions and uncertainty; test adapted heads too |
| It improves agents | Real agent execution and selection using the evaluator | Better independently measured outcomes on fresh tasks at an equal search budget, followed by prospective use |
| More experience creates a shared data flywheel | Source-task training that improves evaluation on unseen targets | Controlled transfer study at equal feedback and compute budgets; report negative transfer |

The first two are engineering properties that can be directly verified. The others are empirical claims about a defined population. “Unhackable,” “20 labels suffice for every workflow,” and “higher reward guarantees better work” are not release promises supported by this research.

## What exists in Stash

The source audit uses GitHub main at `fadc4bd1a4f3af773295335b378837044e826c1e`, rather than the older local checkout.

The automatic workbench calls `step_labeling.annotate`; labels are converted to fixed scores with optional external Jev quality checks. The lightweight rubric head learns over TypeSafe Jev probabilities. A separate worker fine-tunes a sequence classifier on preference pairs. These are useful baselines and infrastructure, but they do not constitute the proposed shared learned representation with a customer residual head. [Automatic workbench](https://github.com/Fergana-Labs/stash/blob/fadc4bd1/backend/services/rm/workbench_auto.py#L136), [rule scoring](https://github.com/Fergana-Labs/stash/blob/fadc4bd1/backend/services/rm/step_scoring.py#L17), [Jev provider](https://github.com/Fergana-Labs/stash/blob/fadc4bd1/backend/services/intuition/providers.py#L1), [learned head](https://github.com/Fergana-Labs/stash/blob/fadc4bd1/backend/services/intuition/head.py#L1), [training worker](https://github.com/Fergana-Labs/stash/blob/fadc4bd1/rm_worker/train.py#L104).

Reuse the permissioned corpus, immutable dataset snapshots, cloud execution, private artifact storage, model registry, release/rollback machinery and instruction-delivery receipts. The online optimizer already assigns real tasks to candidate/incumbent prompts and requires reported business outcomes for promotion. Its customer-reported outcomes still need to be distinguished from independently captured verification. [Shared evaluator](https://github.com/Fergana-Labs/stash/blob/fadc4bd1/docs/reward-models/SHARED_EVALUATOR.md), [online optimization](https://github.com/Fergana-Labs/stash/blob/fadc4bd1/docs/reward-models/CONTINUOUS-OPTIMIZATION.md).

The current shared release gate has minimums of 20 evaluation pairs, 75% accuracy and a one-percentage-point improvement. These are infrastructure gates, not sufficient evidence of generalization or robustness. Stash's GEPA adapter generates a text completion; it does not execute a coding harness. [Release policy](https://github.com/Fergana-Labs/stash/blob/fadc4bd1/rm_worker/release_gate.py#L5), [coding boundary](https://github.com/Fergana-Labs/stash/blob/fadc4bd1/docs/reward-models/CODING-DOGFOOD.md#L77).

Documentation also needs reconciliation: `AGENT-WORKBENCH.md` describes an older direct-Jev policy, whereas the current automatic pipeline uses labels and rules. Record the actual evaluator family and version with every score; historical scores retain their original semantics. Repository code alone does not establish which private checkpoint is currently released in production.

## Recommended architecture

### Train a shared representation for agent work

Use a licensed open-weight reward model as initialization. First freeze its backbone and train a Stash shared projection/reward basis on permissioned task attempts. A candidate basis has 4–8 learned dimensions. This dimension is a hypothesis to test, not a discovered property of customer preferences. Compare a shared LoRA trace adapter if the frozen representation is insufficient; do not assume that more parameter updates improve the product.

LoRe is a close architecture reference: it learns shared reward basis functions and adapts only a low-dimensional weight vector for unseen users. Its few-shot experiments support feasibility, but include synthetic users formed from existing reward-model mixtures, rather than arbitrary enterprise workflows. Study the method and independently implement it: the official code is licensed CC-BY-NC 4.0. [LoRe paper](https://arxiv.org/abs/2504.14439), [official implementation](https://github.com/facebookresearch/LoRe).

Skywork Reward V2 Qwen3-1.7B and 4B are practical cloud baselines. The official 4B model card licenses weights and code Apache-2.0, recommends staying within its trained 16,384-token context, and uses a template without system messages. Consequently, Stash needs its own task/evidence serialization and trace adaptation. Public pretrained weights provide a starting point; downloading them does not substantiate a Stash-trained representation claim. [Official model card](https://huggingface.co/Skywork/Skywork-Reward-V2-Qwen3-4B).

Train on comparisons between attempts at the same task, with substantively different artifacts or outcomes. Preserve requirements, applicable constraints, initial state, recorded tool results and final artifact. Include plausible failures: weakened tests, unsupported answers, silent filtering, wrong tool arguments, omitted requirements and fabricated success. Model-generated negatives remain synthetic until separately adjudicated. Ordinary Bradley–Terry training is a baseline; GRM-style auxiliary language modelling is an ablation for preserving useful shared representations. [GRM](https://arxiv.org/abs/2406.10216).

Begin with completed-episode quality. For action evaluation, define whether a score uses only evidence available before the action or retrospectively uses later results. Train and test these as different interfaces. A hindsight score is not automatically a reward suitable for evaluating an unseen next action. No decay formula or preference score establishes an action's causal contribution to success.

### Adapt the customer head without retraining the backbone

Let `z = shared_basis(task, attempt, evidence)` and define:

```text
customer_reward = (default_weights + customer_residual) · z
```

At zero customer labels, the residual is zero and the released default evaluator serves predictions. With feedback, freeze the shared checkpoint and fit the residual using regularized same-task preferences. Shrink it toward the default head; choose dimension and regularization on source development workflows before evaluating unseen customers. Cache features so head fitting does not require another backbone pass. A change to the shared representation invalidates its feature cache and requires refitting and revalidating customer heads. Keep customers pinned to their compatible incumbent version until that migration passes; never silently apply old customer weights to a new basis.

The dimensions are latent unless separately supervised and validated. Do not label them “correctness” or “safety” merely because they have convenient names. Pairwise score differences support relative preference; they do not by themselves supply an absolute success probability or a universal quality scale.

Compare this architecture against frozen probes and the existing Jev head. PAL also motivates adapting few mixture weights, but its notable 20-example result uses constructed preferences for summary length. It does not establish a universal 20-label guarantee. [PAL author project](https://pal-alignment.github.io/).

If an unfamiliar workflow needs a distinction absent from the shared basis, the head cannot create it. More feedback, a broader shared representation or an explicit unsupported-workflow state may be necessary. Customer preferences must not override independently checked evidence integrity or explicit task constraints.

### Return uncertainty and preserve evidence

Distinguish A preferred, B preferred, genuine tie, and insufficient evidence. Do not convert missing evidence into a neutral score or an agent failure. Explanations cite recorded evidence and are evaluated separately from preference accuracy.

Initially, use held-out calibration and report risk versus coverage: how often predictions are wrong among the cases the evaluator accepts, and how often it abstains. Standard conformal risk control supplies expected-risk bounds under exchangeability and specified loss conditions; ordinary marginal coverage is not a guarantee of accuracy for every accepted customer case. Selective-risk methods such as SCoRE offer a more relevant framework, but their assumptions and exact deployment rule must be implemented and audited. Do not certify adaptive adversarial search by applying a calibration wrapper to unrelated ordinary examples. [Conformal Risk Control](https://arxiv.org/abs/2208.02814), [SCoRE](https://arxiv.org/abs/2603.24704).

## Build reward hacking resistance through attacks and repair

The core loop is: **search for a failure, independently establish that it is a failure, train on the distinction, and attack the new version again.** Adv-RM provides a direct precedent for iterative adversarial reward training. Ensemble disagreement helps discover candidates but cannot establish their ground truth because judges can share errors. [Adversarial Training of Reward Models](https://arxiv.org/abs/2504.06141), [Helping or Herding](https://arxiv.org/abs/2312.09244).

Separate three evaluations: forged trace inputs, genuinely executed agents optimizing a score, and honest distribution shift. An agent's statement that tests passed is not captured test output. Capture authoritative verification outside the agent-editable workspace and preserve its provenance. Audit patches for tampering with tests or evidence before calling a task solved.

Attacks should cover grader instructions inside tool outputs, false completion, hidden failed actions, verbosity and keyword gaming, omitted requirements, invalid tool arguments and test tampering in an owned sandbox. Also test honest impossible tasks, partial results and helpful clarifying questions so defenses do not merely punish legitimate behavior.

Run best-of-N and iterative black-box search at budgets of 1, 4, 16, 64 and 256 candidates or evaluator queries per task; record tokens and runtime as well. Search should maximize Stash reward while minimizing independently verified task quality. Later, add cloud-trained attacker policies and an independent attacker family. Treat a task as compromised if any permitted candidate fools the evaluator; the candidates inside one task are not independent trials.

Freeze attack capabilities, access to scores, allowed edits, task distribution, optimizer, budget, success definition and model/head versions. Repair on development tasks. Final tasks and held-out attack families remain untouched until the release decision. Once a test informs model selection, it is development evidence for subsequent versions.

Static accuracy is insufficient. Reward Under Attack separates perturbation robustness from optimized attacks, and reports math settings in which high process reward coexists with very low actual accuracy. Reward-model overoptimization work also demonstrates divergence between optimized proxy reward and gold reward. Those findings motivate measuring verified outcomes as optimization pressure increases; their numerical results are not forecasts for Stash. [Reward Under Attack](https://proceedings.mlr.press/v306/tiwari26b.html), [Scaling Laws for Reward Model Overoptimization](https://proceedings.mlr.press/v202/gao23h.html).

Goodfire's activation probes are an optional later monitor when the acting model exposes internal states. Their research demonstrates detection, not universal prevention, and does not transfer directly to closed-model APIs. This is not required for the first product. Rubric dropout and pessimistic ensembles are ablations rather than the foundation of a robustness promise. [Goodfire monitoring paper](https://arxiv.org/abs/2609.19101).

## Experiments that decide whether the claims work

### Shared evaluator and few-label adaptation

Hold out whole customers, workflow families, task templates and time periods from shared training. All related sessions, subagents, alternatives and revisions stay together. Use existing public benchmarks as external regression tests, supplemented by newly collected tasks whose training exposure is known. AgentRewardBench contains expert-reviewed web-agent trajectories and finds no single judge best across its benchmarks; it is one test domain, not coverage of all agent work. [AgentRewardBench](https://arxiv.org/abs/2504.08942).

Compare the current rule scorer, Jev head, Qwen-0.6B training, public pretrained reward model, frozen feature probe and proposed shared basis. A task-conditioned generative judge is an additional challenger if scoring features miss important criteria. Match information, label budget and compute; select the strongest simpler baseline on development data.

For each unseen target, evaluate 0, 5, 10, 20, 30, 50 and 100 trusted adaptation comparisons, using repeated independently sampled support sets. A label used to create a rubric, choose examples or tune a prompt counts toward the adaptation budget. Generated variants of one labeled example are not additional independent human labels. Active sampling is a separate experimental arm; the final test population stays representative.

Use a larger independent test set per target, initially planning 100–200 task comparisons as a pilot and then sizing the confirmatory study for the effect worth shipping. Report macro and worst-workflow accuracy, preference log loss, calibration, abstention coverage, runtime and negative transfer. Estimate uncertainty at the customer/task level; hundreds of correlated actions in one trace do not become hundreds of independent samples.

Define the minimum worthwhile improvement and tolerated regressions before the confirmatory experiment. Predeclare the supported workflow groups and primary comparisons; adjust for multiple comparisons or confirm selected groups on a new untouched sample. Claim 20–30-label adaptation only where the improvement interval clears the predeclared worthwhile-effect threshold against both the zero-label model and the strongest simpler adaptation baseline. Report uncertainty and label provenance. Quality may require more labels in other workflows.

### Robustness under optimization

After fitting each customer head, repeat adaptive attacks on distinct tasks. Compare attack success, clean quality and abstention under equal budgets. Plot actual outcomes alongside predicted reward through increasing search intensity. A model that only improves static attack accuracy does not pass the optimization claim.

Statistical illustrations for a frozen evaluation protocol with independent representative task campaigns and zero compromises:

| Independent campaigns | One-sided exact 95% upper bound on compromise probability |
|---:|---:|
| 20 | 13.91% |
| 30 | 9.50% |
| 60 | 4.87% |
| 100 | 2.95% |
| 299 | 1.00% approximately, just below 1% |

These values use `1 - 0.05^(1/n)` and were calculated directly. They are not Stash results or required universal thresholds. Correlated campaigns, tuning on the final evaluation set, adaptation across final campaigns, repeated peeking without sequential correction, or changes to the target population invalidate this simple interpretation. Attackers may be tuned on development data and adapt within each task under the frozen algorithm and budget. Twenty labels to fit a head are distinct from enough untouched evidence to validate a low error rate.

### Actual agent improvement

Replace the text-completion GEPA adapter with an execution adapter for one reproducible Stash-owned workflow. Capture repository base state, initial overlays, dependencies, task instructions and verification commands. Run the same coding agent with incumbent and candidate skills on fresh tasks. Preserve independently observed patches, test results, violations, runtime and cost. Do not edit a customer's repository as part of this experiment.

Use the same search budget across evaluators. Optimization tasks guide selection; separate final tasks measure outcomes. A generated skill's higher reward is not the endpoint. Release it only if independently measured completion improves without unacceptable regressions, then record the skill version actually loaded in subsequent sessions. Judge releases and skill releases have separate gates. GEPA supports program-level evaluation through adapters; Stash must supply the real execution adapter. [GEPA paper](https://arxiv.org/abs/2507.19457).

For subjective tasks without executable outcomes, use blinded human adjudication. Prediction-powered inference can combine a representative human audit sample with many model predictions to estimate aggregate outcomes with uncertainty; it cannot establish that each model label is true or eliminate the audit sample. Keep this optional until the basic outcome measurement works. [Prediction-Powered Inference](https://arxiv.org/abs/2301.09633).

### Cross-workflow transfer

At equal labeling and compute budgets, compare shared training on A against A+B and A+B+C, then evaluate a wholly unseen target D at the same adaptation budget. Adding source experience must improve D to substantiate a compounding shared capability. Improved customer-specific scores alone establish personalization. Preserve consent for pooled training and report when unrelated experience hurts.

## Implementation sequence

| Stage | Concrete changes | Completion evidence |
|---|---|---|
| 1. Define evidence and benchmarks | Add a completed-episode contract and dataset manifest; retain task-group, outcome-source, license/consent and partition lineage. Reconcile evaluator documentation. | Representative owned/sandbox tasks have independently adjudicated labels; related examples cannot cross partitions. |
| 2. Add the shared model and head | Extend cloud training/scoring for a learned shared basis and optional adapter; add a customer-head artifact linked to a frozen shared version; reuse head fitting and registry infrastructure. | Reproducible checkpoint, zero-label serving smoke test, parameter audit showing head-only customer updates, consistent train/serve serialization and validated head migration across shared versions. |
| 3. Route production scores explicitly | Add evaluator-family/version metadata and serving selection to the workbench. Keep old rule/teacher outputs as distinct historical/diagnostic records. | Default displayed scores demonstrably come from the released checkpoint; no silent switch between scoring semantics. |
| 4. Validate adaptation and attacks | Extend release reports/gates for learning curves, untouched target partitions, attack budgets, outcome divergence and uncertainty. | Frozen independent reports meet preregistered product thresholds; failed heads retain the incumbent or abstain. |
| 5. Execute agent tasks | Add replay capture and a real harness adapter; use independent checks for release. Reuse prompt comparison and instruction-delivery infrastructure. | Paired fresh-task outcomes improve and the accepted skill is captured in later matching sessions. |
| 6. Test transfer and prospective benefit | Add controlled source-data transfer studies and monitored real-use comparisons. | Unseen-workflow benefit at equal feedback budget and prospective outcomes; scope the claim to supported populations. |

Suggested code locations are `backend/services/rm/evaluator.py`, `jobs.py`, `workbench_auto.py`, `workbench_evaluation.py`, a new customer-head service, `rm_worker/train.py`, `scoring.py`, `release_gate.py`, and a new execution adapter used by `gepa_run.py`. Keep the existing Jev head and scalar fine-tuning paths as baselines until evidence supports replacement. Changes to schema and defaults follow the model/evidence contracts, not the other way around.

The existing untracked completed-task proposal contains compatible ideas but marks itself superseded. This plan uses its completed-task, separate-release and independent-evaluation principles as hypotheses; it does not treat it as the authoritative current product specification.

## Release statement after validation

The architecture statement can become: “Stash provides a pretrained evaluator built on open weights with a shared representation trained by us. It adapts to a customer by updating a small head.”

The evidence statement should contain measured values: “On these held-out workflows, 20–30 trusted customer comparisons improved quality by X. At Y attacker queries per task, compromise fell from A to B. At the same optimization budget, independently verified agent completion improved by D.” Publish denominators, intervals, model versions, supported contexts and unresolved failure classes.

Research establishes a credible route to those statements. The model training, adaptation studies, adversarial campaigns and actual-agent experiments remain to be run. All substantial training, batch inference and agent replay compute belongs in the cloud; this research launched none of it.
