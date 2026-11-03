# Reward functions through MCP

The `stash-mcp` server can create and use the judge evals shown in Stash's Evals
UI. It uses the existing `/api/v1/evals` API with the CLI's account and workspace
credentials; reward-model access and ownership checks still apply.

Call `stash_reward_function_create` with a name, instructions and 1-12 traits:

```json
{
  "name": "General knowledge work",
  "instructions": "Judge whether the work fulfills the user's request accurately and clearly.",
  "traits": [
    {
      "name": "Task completion",
      "good": "Completes the requested work and verifies the result.",
      "bad": "Only proposes a plan, or claims completion without evidence.",
      "basis": "The user wants completed work."
    }
  ]
}
```

Creation saves an explicit rubric and returns the eval's `id`, `ready`, `version`
and scoring `endpoint`. No labeled examples are invented and no model training
is needed. The initial scoring rule averages trait grades; hard-failure semantics
must be expressed in the rubric, not assumed from a trait's name. This is an LLM
judge, not a deterministic validator.

Use `stash_reward_function_score` with the returned `eval_id` and
`output: {"text": "the work to judge"}`. Optional `output.images` accepts base64
or data URLs; `trace` carries conversation context. The response includes a 0-1
score, grades, reasons, fixes and a logged `call_id`. The call runs the hosted
judge and records the submitted work but does not label it as training data.
Supply `change` and/or `before` only when judging an edit instead of the whole
output.

`stash_reward_function_list` discovers functions. `stash_reward_function_get`
reads the current definition. To replace a rubric, pass its current `version`
as `base_version` to `stash_reward_function_set_rubric` (use 0 if the version is
null). Concurrent edits return a conflict instead of overwriting newer work.
The API preserves explicitly written traits during later automatic revisions.

Creation uses two API writes. If the second write or verification fails, the
error includes the created ID. Read that function, then repair its rubric if
needed. Do not repeat creation and leave duplicates.

Update the installed `stashai` package and restart the MCP connection to discover
these tools after installing a release that includes them.
