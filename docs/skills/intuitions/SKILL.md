---
name: intuitions
description: Check your work against the user's own judgments (intuition models) before you call it done, and feed their corrections back.
when_to_use: Before finishing any task whose output the user judges by taste or standards they've encoded — a drafted reply, a summary, a web-agent result, a PR — and whenever the user corrects a verdict.
version: "1"
---

# Checking work against the user's intuitions

An intuition model is one of the user's judgments, made explicit: a few rubric
questions the Jev judge answers about an item, and a small calibrated head that
turns those answers into the user's verdict ("send / edit / rewrite", "did the
agent really finish?"). Each one says in `when_to_use` what it applies to, the
same way a skill does.

Treat them like a linter that knows the user's taste. They're cheap, they log
every call so the user can see what you checked, and they get better when the
user corrects them.

## Before you finish

1. Find what applies. Call `stash_intuition_find(task=...)` with a sentence
   describing the output you produced, or read `when_to_use` from
   `stash_intuition_list` and pick yourself. No match means no check; don't
   force one.
2. Check the output. Call `stash_intuition_check(item=..., model_ids=[...])`.
   Pass the item in the shape the model's examples use (`stash_intuition_get`
   shows them). For web-agent results, keep agent-written text
   (`agent_final_message`) separate from what the environment recorded
   (`environment_final_page`); the model only trusts the latter.
3. Act on findings. `passed: false` means some model landed on a label the user
   flagged as "needs fixing". Each finding's `why` lists the rubric answers
   that drove it. Fix those specific things and check again. Stop after two
   rounds; if it still fails, report the finding and its `why` instead of
   guessing.
4. Mind the confidence. Below ~0.65, treat a verdict as a hint, and say so if
   it matters.

Never word your output to satisfy a rubric question without actually changing
the substance. The models are trained against that, and the user will see it in
the logged calls.

## When the user corrects a verdict

If the user disagrees with a verdict you got (by `prediction_id`), call
`stash_intuition_review(model_id, prediction_id, label=<their label>)`. That
turns the correction into a training example for the next version. Don't train
or promote yourself unless the user asks: `stash_intuition_train` fits a draft
and returns the promotion gate, and `stash_intuition_promote` only goes through
when the gate passes.

## Evals

To score a batch of outputs (a dataset, a prompt change, an A/B), call
`stash_intuition_batch(model_id, items, labels?)`. It runs up to 200 items,
returns the label distribution and how many were flagged, and also accuracy,
log loss and Brier score when you pass labels. Batch calls stay out of the
user's review inbox.
