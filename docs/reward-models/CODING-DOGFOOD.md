# Personal coding reward models

Step 1 imports coding sessions. Step 2 builds a small, inspectable reward model
from context-matched action comparisons. This is an experimental evaluator;
pairwise agreement with AI labels does not establish better coding outcomes.

## Create a model

Select completed coding tasks in Traces, open **Options**, set the reward
criteria (one per line), and create a model. The UI uses action input version 3.
The server reserves a deterministic subset of the selected traces for evaluation.
Select independent tasks: the UI currently cannot group related sessions.

For multiple sessions or subagents from the same task, use the existing
`POST /api/v1/rm/reward-models` API with an explicit group map:

```json
{
  "name": "coding-quality-v1",
  "trace_ids": ["<implementation-trace-uuid>", "<related-agent-trace-uuid>", "<independent-task-uuid>"],
  "epochs": 1,
  "training_config": {
    "input_version": 3,
    "rubric": [
      "Complete the actual task correctly using available evidence.",
      "Respect explicit constraints and repository boundaries.",
      "Use proportionate verification and report what was checked.",
      "Make efficient, targeted progress without redundant work.",
      "Report results and limitations accurately and concisely."
    ],
    "max_actions_per_trace": 24,
    "task_groups": {
      "<implementation-trace-uuid>": "implementation",
      "<related-agent-trace-uuid>": "implementation",
      "<independent-task-uuid>": "held-out-task"
    },
    "evaluation_groups": ["held-out-task"]
  }
}
```

The immutable model configuration records the criteria and task split before
extraction. Training samples up to 24 actions per trace by default, spanning
tool calls and text responses across the session. Oversized actions (over 3,500
characters) and internal thinking are excluded as training targets. Malformed
judgments are retried once, then abstain. API or authentication failures still
fail the job. Every accepted comparison has a separate model review, using only
context available at the action. User feedback is attributed separately from AI
judgments; harness-injected teammate messages are not human feedback.

Version 3 uses only same-context action comparisons. It does not use cross-task
aggregate ratings as preferences. At least two training pairs and one held-out
pair must survive review, with no shared task groups or duplicate examples.
An insufficient dataset fails rather than falling back to evaluation on training
data. The database stores the actual extracted pairs and their partition.

## Inspect and use the result

**Models → View learning** shows the source, reason, original action, alternative,
and whether each comparison was used for training or held-out evaluation.
Review these before trusting the scores. AI review is not human approval and can
still miss unsupported assumptions or reward easy, unrepresentative alternatives.

Initial scoring covers the sampled actions in the selected tasks. Score another
trace with `POST /api/v1/rm/traces/{id}/score` and the personal `reward_model_id`.
Scores are relative preferences, not probabilities of correctness. Training does
not change the shared evaluator, contribution consent, or auto-score every future
trace. Existing requests without `training_config` retain the legacy behavior.

The worker saves the input version, criteria, and 4,096-token context window with
the checkpoint. Instructions, initial task, latest request, recent history, action,
and rubric receive fixed token budgets (24/14/14/22/20/6 percent). Long sections
are explicitly clipped. This preserves anchors from long sessions, not their
entire history, and does not guarantee every relevant instruction survives.
Training, scoring, evaluation, and skill optimization use the saved format.

GEPA excludes these held-out task groups and their feedback from skill generation.
The evaluator sees the original task context and candidate response; it never
sees the candidate skill as part of the grading context. The current GEPA path
generates responses from trace prompts. It does **not** replay a real coding
harness, apply a patch, or run repository tests. Before installing a generated
skill as an improvement, compare actual coding outcomes with and without it on
fresh tasks. That is the next stage of dogfooding.

Real training runs on the configured remote worker (`RM_COMPUTE=modal`). Local
worker tests use a random model with fewer than 20,000 parameters and no model
downloads. Do not run real model training on a developer laptop.
