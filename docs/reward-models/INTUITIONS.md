# Intuition models

An intuition model is one person's judgment, made into a small model that
agents can call: "would our support lead send this reply?", "did the web agent
actually finish?". Stash is where people build them, check what they decided
and why, correct them, and serve them as an API, an MCP tool, or a linter step
in an agent's loop.

It's a thin, inspectable layer over Jev (TypeSafe's typed judge). Jev answers
narrow, typed questions about an item; the intuition model decides which
questions to ask and how much each answer counts for this person.

## Anatomy

A **version** is frozen and fully editable as a draft:

| Part | What it is | Who changes it |
|---|---|---|
| Description | What's being judged and what the person cares about. Jev sees it as context. | User, or Claude's draft |
| Labels | The output space (`send / edit / rewrite`), each with a description. Labels marked `flag` mean "needs fixing", and checks report them. | User |
| Rubric | Up to 12 typed questions (yes/no, choice, score) Jev answers per item. | User, Draft rubric, Suggest question |
| Seed examples | A few labeled items shown to Jev as reference. | User |
| Head | Logistic regression over the answer probabilities (multinomial for choice, Bradley–Terry for preference), temperature-calibrated out of fold. Weights are readable and editable. | Fit, or hand-edited |

Model-level (not versioned): the name, and **`when_to_use`**, which works
like a skill's description. Agents read it to decide whether the judgment
applies to what they're doing.

## Loop

1. **Collect.** Label examples in the UI, import them, generate them with
   Claude, or label production calls from the review inbox. Every served
   prediction is logged with its version, caller, confidence and drivers.
2. **Improve one judgment at a time.** After a fit, each rubric question shows
   its mean answer per label, and the held-out accuracy and log loss without it
   (an ablation). A question that doesn't separate the labels, or doesn't help
   held-out accuracy, is the one to rewrite or drop. This replaces "edit the
   prompt, rerun the whole eval".
3. **Fit and gate.** Refitting never calls the judge, since answers are cached
   per (item, question context). A draft is promoted only if it doesn't lose
   held-out accuracy and doesn't lose more than 0.02 log loss against the
   active version. Rollback restores any earlier version.
4. **Serve.** Calls return the label, calibrated probabilities, the rubric
   answers, and `drivers`: each question's push toward the verdict.

## Agent surface

| Use | REST | MCP |
|---|---|---|
| Which judgments apply to this task? | `GET /api/v1/intuitions/find?task=` | `stash_intuition_find` |
| Lint an output (several models; findings = flagged labels, with why) | `POST /api/v1/intuitions/check` | `stash_intuition_check` |
| Judge one item / compare two | `POST /{id}/predict`, `/{id}/compare` | `stash_intuition_predict`, `_compare` |
| Eval over a dataset (≤200; accuracy, log loss, Brier with labels) | `POST /{id}/batch` | `stash_intuition_batch` |
| Feed back a correction | `POST /{id}/predictions/{pid}/review` | `stash_intuition_review` |
| Author, train, promote | draft routes | `_create`, `_edit_draft`, `_train`, `_promote`, `_set_when_to_use` |

The `intuitions` skill (`docs/skills/intuitions/SKILL.md`) teaches an agent
the habit: find the relevant models, check before finishing, fix the findings,
and send corrections back.

## Bundled examples

- **Support reply: ready to send?** Hand-written examples for a fictional
  store, labeled send/edit/rewrite. v2 adds a question about risky promises.
- **Web agent: did it actually finish?** 64 AgentRewardBench trajectories
  with expert labels, split by provenance (`agent_trajectory`,
  `agent_final_message`, `environment_final_page`). v2 adds a question about
  formulaic success claims. The inbox includes one trajectory with a forged
  "[SYSTEM LOG] … status=SUCCESS" line appended.

Both ship with recorded Jev answers, so loading them makes no judge calls.
(Check AgentRewardBench's license terms before a public launch.)

## Evidence

`scripts/intuition_eval/RESULTS.md` has the full numbers. In short:

- **The head helps where the decision breaks into checkable facts, and always
  helps calibration.** AgentRewardBench: raw Jev 72% → rubric head 79–84%,
  Brier skill +0.26 → +0.47. Raw Jev is still better when the description
  already states the rule (the support demo), and on side-by-side taste.
- **Provenance helps against forged evidence.** Optimization attacks append
  fake logs and fake steps to flat transcripts. Splitting agent-written text
  from environment-recorded text raised rubric-head accuracy from 79% to 83%,
  and halved best-of-32 attack success for raw Jev (32% → 14%) and the rubric
  head (27% → 18%). Samples are small, and iterative attacks on the split
  format are still pending.
- **RL against the judge (GSM8K GRPO):** no injected text or fake answer claims
  turned up in the trained models' answers. The heads gave the fastest early
  gains (84% by step 160). Their failure mode was answers growing until they hit the
  length limit. The robust judge stayed strict; raw Jev drifted toward passing
  wrong answers.
- **Hide head weights and rubric answers from untrusted callers** if they
  might be optimizing against the model. White-box attacks did 11–17 points
  better.
