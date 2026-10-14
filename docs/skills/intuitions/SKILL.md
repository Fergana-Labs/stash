---
name: intuitions
description: Build, run and improve Stash intuitions — small calibrated classifiers that capture a person's judgment from a handful of labeled examples — over MCP or REST.
when_to_use: When an agent needs a check that matches a person's judgment (verify its own output before acting, flag issues, route items, grade outputs, pick the better of two), or the user asks to build, train, test or improve a classifier, judge, eval, grader, or reward from examples.
version: "1"
---

# Intuitions

An intuition is a classifier that matches one person's judgment call. Under the
hood it is not a fine-tuned model:

- **Jev**, a judge model, answers each **criterion** (an observable yes/no or
  multiple-choice question about the input) and the task itself, zero-shot.
  Every answer comes back as a probability.
- A small **calibrated head** learns from the person's labels how much each
  answer matters. It starts from "trust the zero-shot answer", so 6–10 labels
  already help.
- An **embedding probe** learns what the labeled examples look like, beyond what
  the criteria say.
- Accuracy is always measured on **held-out** examples the head never trained on.

Three kinds:

| `output_type` | Decision | Example label |
|---|---|---|
| `choice` | exactly one of 2–12 labels | `billing` |
| `multi` | any subset of 1–8 issues, or none | `background+watermark`, `none` |
| `preference` | good/bad, or the better of two | `good`, `a` |

## Connect

**MCP** (preferred): streamable HTTP at `https://<your stash host>/mcp/intuitions`,
with header `Authorization: Bearer <Stash API key>`.

```json
{"mcpServers": {"stash-intuitions": {"type": "http",
  "url": "https://joinstash.ai/mcp/intuitions",
  "headers": {"Authorization": "Bearer st_..."}}}}
```

**REST**: the same bearer token against `/api/v1/intuitions` and
`/api/v1/model-wizard`. Classifying one input:

```bash
curl -s https://joinstash.ai/api/v1/intuitions/$ID/predict \
  -H "Authorization: Bearer $STASH_API_KEY" -H 'Content-Type: application/json' \
  -d '{"item": "text, or a JSON object", "ref": "your-id-for-feedback"}'
```

## Build one well

Do these in order. Skip what the person already told you, and never ask more
than two questions at a time.

1. **One decision.** What is decided, by whom, and what happens next? If the
   person describes two decisions, build one now and offer the other next.
2. **Real inputs first.** Ask for one or two real examples before talking
   about labels.
3. **Labels with boundaries.** Every label needs a definition *and* the nearest
   thing it is not. Ask for the hardest borderline case and what the right call
   is; this is where most classifiers go wrong. If several things can be true of
   one input at once, use `multi`.
4. **Stakes.** Which mistake is worse? Which cases must it never get wrong?
   Add those as labeled, `pinned` examples: no version can ship if it gets a
   pinned case wrong.
5. **Brief.** Record all of the above with `save_brief`. It is compiled into the
   instructions the judge reads, so keep it accurate.
6. **Examples.** Get 8+ confirmed labels with every label present, mostly real
   and hard. **Real data first:** ask where real cases live (exports, logs,
   tickets, past decisions). Only if the person can't provide them, or their
   data lacks a kind of case, use `generate_examples` aimed at that gap. Drafts
   come with a suggested label and reason, and **a person must confirm them**
   (`label_example`, or `accept_suggestions` only when they say so). Never
   invent labels yourself.
7. **Criteria.** 3–6 observable properties. Once both kinds of label exist,
   `propose_criteria` with mode `contrastive` finds what separates similar items
   that were labeled differently. Save them with `set_criteria`.
8. **Train**, then report held-out accuracy **with its sample size**, next to
   zero-shot Jev. With fewer than about 20 held-out examples, call it an early
   estimate.
9. **Ship** when the gate passes.

## Use it

| Use | How |
|---|---|
| Verify inside an agent loop | `classify` the draft before acting; retry or escalate on a bad label or low confidence. |
| Monitor production | `classify` real traffic with a `ref`. Low-confidence calls land in the inbox. |
| Regression-test evals | Pin must-never cases. Training reports what each new version fixed and broke. |
| Prompt optimization | Use `P(good)`, or a label's probability, as the score to maximize. |
| Post-training reward | The same scores as a reward. Calibrated probabilities make it a smooth signal. |

## Keep it improving

- `inbox` lists recent decisions, least confident first. `review_prediction`
  confirms or corrects one, **with a reason**. It becomes a golden example and
  can be pinned.
- `give_feedback` records downstream outcomes against a `prediction_id` or your
  own `ref`.
- Reasons from corrections drive new criteria; `train` again after a batch of
  corrections.

## MCP tools

`list_intuitions`, `create_intuition`, `get_intuition`, `save_brief`,
`add_examples`, `generate_examples`, `list_examples`, `label_example`,
`accept_suggestions`, `propose_criteria`, `set_criteria`, `train`, `ship`,
`classify`, `inbox`, `review_prediction`, `give_feedback`.
