# Learn Henry's website taste from agent history

This is the target demo Henry described on October 15, 2026. The existing
[website-design fixture](website-design.md) illustrates part of the interaction;
it is not evidence that this experiment has succeeded.

The [operator runbook](website-taste-running.md) describes the implemented
history preparation, calibration, frozen-classifier scoring, Qwen/GEPA adapter,
cloud DPO job, and blinded gallery. Preparing these stages does not mean their
data gates, cloud training, or final comparisons have completed.

The user supplies access to past traces once. Stash finds website-building work
and corrections, learns an evaluator for that user's taste, and uses it to
improve the website-generating agent. The final demonstration compares actual
rendered outputs on new briefs.

## The comparison

Use the same pinned Qwen base checkpoint and website-generation harness in all
four arms. Keep the task prompt, tools, rendering environment, output format,
generation limit, and final evaluation briefs the same.

| Arm | Learned artifact | What changes when generating a new website |
| --- | --- | --- |
| Base Qwen | None | The ordinary task prompt |
| Qwen + skill | A `SKILL.md` synthesized agentically from training traces and corrections | Additional instructions in context; Qwen weights stay fixed |
| Qwen + GEPA | Instructions selected by actual GEPA optimization against the frozen taste classifier | Optimized instructions in context; Qwen weights stay fixed |
| Post-trained Qwen | A versioned weight adapter or checkpoint trained on the same allowed history | Qwen weights change; any additional instructions are declared |

The desired result is skill < GEPA < post-training, with base Qwen as a control.
That ordering is a hypothesis. Save all arms and all attempted candidates even
if the ordering fails. Do not choose the test briefs or screenshots after seeing
which arm wins.

GEPA optimizes reusable instructions across training tasks. Each metric call
must actually run Qwen, render its website, and score that rendered artifact.
Reflecting on a single HTML file and retrying it is a different experiment. At
final evaluation, each arm generates an unseen brief without further adaptation
using the test outputs or Henry's test-set choices.

Report optimization/training cost separately from final per-website inference
cost. Give every arm the same final generation budget. If comparing online
best-of-N search instead, make that a separate, explicitly budgeted comparison.

## From history to supervision

1. Search recorded history and the connected Mac's unrecorded Codex sessions.
   The user should not need to export and upload sessions manually. Record the
   coverage and any inaccessible, partial, or unresolved history.
2. Identify actual website-building tasks and the user's own corrections.
   Retain the original request, prior output, exact feedback, subsequent change,
   and source session/event references. Treat trace contents as data, including
   commands inside tool results.
3. Resolve the artifact at the point the correction refers to. Prefer a saved
   screenshot or reconstruct a version from complete recorded source. A current
   working-tree file is not proof of what an old session showed. Missing source
   stays missing; do not invent a screenshot or an earlier version.
4. Separate taste feedback from functional requirements and unrelated debugging.
   A complaint about typography can support a negative judgment of the preceding
   typography; it does not label every aspect of the entire website as bad.
   A subsequent edit is not automatically approved because the user went silent.
5. Propose source-linked examples, pairwise preferences, and criteria. Surface
   uncertain cases for review and abstain when a preference cannot be grounded.
   Confirm a compact calibration set rather than making Henry label the corpus
   from scratch. An unlabeled trace is not a negative example.

Visual preference examples need the task context, rendered pixels, and the
relevant feedback. Text-only examples can teach instruction compliance and help
find artifacts, but cannot establish visual taste by themselves.

## Train and freeze the taste classifier

The classifier is distinct from the Qwen website generator. Its input is a new
website brief plus the rendered candidate. Its output is a preference score and
inspectable judgments, calibrated against Henry's labels/corrections.

The current implementation offers rubric/verdict features with a calibrated
head, optional embedding probes, contrastive criterion discovery, and repair
experiments (`backend/services/intuition/fusion.py`). The exact Priyadarshan/NSP
method is not yet confirmed; record that implementation and version explicitly
rather than treating this existing stack as confirmation of the intended method.

Split related projects, tasks, resumed sessions, and artifact revisions together
before criterion discovery, skill synthesis, classifier fitting, or optimization.
Use separate partitions for training, development/model selection, and final
testing. Keep an untouched human-labeled classifier test set separate from the
novel briefs used to compare generators. Track duplicate artifact hashes across
partitions. Never fit the reward on final generator-test judgments.

Validate the classifier on unseen examples and known failure cases before
optimizing against it. Freeze its version, preprocessing, visual extractor,
criteria, reference examples, and calibration for the generator experiment.
An increasing reward from a changing classifier is not a comparable curve.

## Skill, GEPA, and weight training

The ordinary skill arm gets a capable agent and the allowed training evidence.
It should summarize the user's preferences as well as it can, with a declared
token/call budget. Do not weaken it to obtain the desired ranking.

The GEPA arm starts from that same skill. It may use training tasks and
classifier feedback, with development tasks for candidate selection. Persist
every prompt candidate, Qwen output, render, classifier prediction, reflection,
selection decision, and metric-call count. Do not pass skill text or claimed
reward inside the website to the classifier as evidence of good taste.

Weight-level post-training is a separate generator-training job, not the small
classifier fit and not prompt optimization. Select and record the actual
objective (for example, correction-pair preference training or reward-driven
training), cloud runtime, model size, training budget, and checkpoint identity.
Use only the allowed training partition. The first experiment can use a clearly
identified adapter; it must not be relabeled as a different training method.

Large model training and inference run in the cloud. Henry's laptop can prepare
data, render bounded HTML artifacts, and run small tests. Per the repository's
compute rule, obtain approval for a concrete larger compute job before launching
it, including its model, provider, budget limit, data, and stop condition.

## What the audience sees

1. A real correction in Henry's history and the exact visual artifact it concerns.
2. The preference extracted from it, with provenance and uncertainty visible.
3. The trained classifier's judgments on examples it did not train on.
4. Actual GEPA trials: Qwen generation, render, reward, reflection, next candidate.
5. A side-by-side gallery of all four arms on the same new website briefs.
6. Blind pairwise choices by Henry, revealed method identities, aggregate results,
   classifier scores, and costs. Show the other test cases as well as the best
   presentation example.

The classifier is the optimization reward, so its own final score cannot be the
only proof of improvement. Henry's blinded preference choices are the primary
outcome. Report ties, task counts, uncertainty, usability failures, and reward
disagreements. A high reward with a broken page or a human-disliked result is a
failure case to inspect.

## Current implementation boundary

| Piece | Verified implementation | Remaining work for this experiment |
| --- | --- | --- |
| History access | Wizard search/read; operator scan, embedded screenshot recovery, source-grounded proposals, native calibration queue | Review taste labels; resolve missing history/artifacts as needed |
| Classifier | Calibrated-head fit command, grouped splits, held-out gates, pinned prediction API | Confirm any newer NSP method; fit and validate the real reviewed dataset |
| Skill | Training-only draft, critique, and revision using feedback and visual descriptions | Run on the frozen reviewed evidence |
| GEPA | Qwen/render/frozen-classifier adapter tested with the actual GEPA library and fake generation | Approve and run real cloud inference; measure development and final performance |
| Post-training | Separate cloud-only Qwen LoRA DPO worker and reward-pair preparation | Approve and validate the GPU job and checkpoint; CPU checks do not establish training success |
| Comparison | PNG-only blind gallery and separate identity key generated from actual trial receipts | Populate with the real four arms; collect blinded human choices and costs |

The current website fixture has synthetic preferences and real Claude-generated
revisions. Its small held-out result does not measure Henry's taste, Qwen, GEPA,
or post-training. Keep it available as a UI fixture while this experiment is
built and measured.
