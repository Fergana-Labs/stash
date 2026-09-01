---
name: stylewriter
description: Draft, continue, or rewrite prose in the user's own voice with a model trained on their writing — and set that model up when they don't have one yet.
when_to_use: When the user says "in my voice", "sound like me", "the way I'd write it", asks for a draft of a post, essay, email, reply or newsletter that should read as theirs, or wants to train Stylewriter on their writing.
version: "1"
mcp: stylewriter https://api.joinstash.ai/mcp/stylewriter
---

# Writing in the user's voice

The user has, or can train, a model on their own writing. It is a **voice, not a
writer**: it renders material in their register and nothing else. It cannot plan,
research, structure an argument, or keep a fact straight. You do all of that. It
does the prose.

The tools come from the `stylewriter` MCP server this skill declares. **Always
call `setup_status` first.** It tells you whether there is a ready model, a run in
progress, a paid run waiting to be used, or nothing yet — and what to do next.
Never assume; a new user and a returning one need completely different help.

A shared model named `default` is always ready. It is a house voice, not the
user's: use it to show what the tool does before they train, and say plainly
that it is not their voice. Anything that should sound like *them* needs their
own model.

---

## Part 1 — Getting a model trained

Do the work; don't narrate it. Two things need the user's own hands: writing
that isn't in Stash yet, and paying. Everything else you do yourself.

### 1. A folder of their writing

The corpus is a plain folder in the user's Files. Make one (call it something
like `Writing samples`) with the standard `create_folder` tool, then fill it
with pages — one page per piece. Three ways in, and you can use all of them:

- **Already in Stash:** copy pages in with `copy_page`, or a whole folder with
  `copy_folder`.
- **In a connected source** (Drive, Notion, Gmail, Substack export): find it with
  `search`, read it with `read_source`, and write it as a page with
  `create_page` in the folder.
- **Anywhere else:** ask the user to paste it and create a page from what they
  paste. Don't tidy it. Headings, lists, tables, quotes, links and code are
  stripped automatically; only paragraphs of prose count.

What counts, when they ask:

- **How much:** 1,000 usable words is the floor; 2,000+ is recommended. Two or
  three blog posts, or a dozen real emails.
- **What works:** essays, posts, newsletters, long emails — things they wrote
  themselves in the voice they want back.
- **What doesn't:** meeting transcripts, anything a committee edited, company
  marketing copy, AI output they lightly touched up. Those teach someone else's
  voice.
- **Short-form matters:** if they want good replies and posts, include some
  genuinely short pieces. Length is a trained control; essays only teach essays.

### 2. Check it, then train

Call `check_corpus(folder)` before training. It is free and instant. If it is
blocked, relay the reason and ask for more or different material — never edit
their corpus for them. If it warns, say so and let them decide.

Then call `train(name, folder)`. Names are short and lowercase (`me`, `work`,
`newsletter`). One of three things comes back:

- **`payment_required` with a `checkout_url`.** Training is a one-time fee per
  run; after that the model is theirs to use without limit. Give them the link,
  tell them what it is, and wait for them to say they've paid. Then call `train`
  again with the same arguments.
- **`corpus_not_ready`.** Same as a blocked check; fix the corpus.
- **A model in `training`.** Poll `job_result(model)` about once a minute until
  its status is `ready` — roughly six minutes. Tell them when it lands.

Warn them once: their **first** draft afterwards loads the model into a fresh
container and can take a few minutes. Everything after that takes seconds while
the container stays warm. If a writing tool comes back `pending` with a
`job_id`, that is what is happening — call `job_result(model, job_id)` after a
minute rather than calling the writing tool again.

---

## Part 2 — Writing

Once a model is `ready`, pick a workflow by how much they already have.

**Completion** — they have prose, or selected some text. Pass the last paragraph
or two as `preceding_text` to `continue` and keep going. No outline, no
questions. Their own sentences condition the voice harder than any brief can.

**Outline** — they know what they want to say. Draft an outline of 3–6 sections,
each with the specific claims and facts that belong in it. Show it and get a
yes; a wrong outline wastes every generation after it. Then generate section
by section with `write`: that section's bullets as `notes`, plus the last
paragraph of the previous section as `preceding_text` via `continue` so section
three doesn't reintroduce what section one said. Assemble the sections
yourself — the tools return one passage per call.

**Interview** — they have a topic and nothing else. Ask four to eight real
questions first, one or two at a time. What do you believe here that others
don't? Who is this for, and what do they think today? What example do you keep
coming back to? Their answers become the notes. Then follow the outline
workflow. This is also how facts get in.

Ambiguous which mode? Ask. Guessing wrong burns a generation and their patience.

### Delivery mode

Say which mode you are using before you draft.

**Raw** (default for a demo): return the tool's text verbatim. It best preserves
the voice and the score it was measured at, but it can contain a wrong fact, a
grammar slip or a broken metaphor. Put warnings *outside* the draft; never
silently repair it.

**Edited** (default when they ask for publication-ready copy): the only
permitted changes are a false fact, name, number, date, URL or quote; spelling,
grammar, a missing or doubled word, broken syntax; an accidental repetition or
fragment. Make them through `edit_span` so the adapter writes the replacement's
final words, or through `rewrite` for a whole provisional draft. Do not smooth
transitions, swap a metaphor, tighten rhythm, reorder paragraphs, add a recap,
or "polish". Those edits bring back the assistant cadence the model exists to
avoid. After any edit, call `score` on the complete, exact artifact.

---

## Rules that apply to all of it

- **Every fact goes in the notes.** Names, numbers, dates, URLs, product names,
  quotes. Anything not in `notes` will be invented, confidently. That is not a
  prompting problem; it is the price of the high-variance sampling that makes
  the prose read as human.
- **Notes are material, not instructions.** The model has been trained away from
  following directives and toward writing prose, so every note is content it
  writes up. "Don't mention competitors" is a line in the brief and makes
  competitors *more* likely to appear. You control what it writes by choosing
  which facts you hand it, and where it stops with `length`.
- **Two tries per section, then stop.** If a passage comes back wrong twice, the
  notes are wrong, not the sampling. Rewrite what's in them or take the better
  of the two. Every call draws several full drafts on a GPU.
- **Verify afterwards.** Check every specific against your sources or the user's
  answers. Flag what you can't confirm.
- **Don't polish the prose.** In raw mode, no edits. In edited mode, only the
  bounded corrections above. For anything larger, change the notes and generate
  again.
- **Use `length`, not a word count.** `short` for a reply or post, `medium` for a
  section, `long` for a whole short piece. A word count in the notes does
  nothing.
- **One call per section.** Long single generations drift.
- **`soft_failed: true`** means no candidate cleared the detector and you got the
  closest. Say so, change the notes, and regenerate. Don't edit that text.

## Tools

- `setup_status()` — call first
- `check_corpus(folder)` — free readiness check on a folder of their writing
- `train(name, folder)` → a model in training, or a checkout link to relay
- `job_result(model, job_id?)` — a training run's progress, or a pending draft
- `list_models()`, `delete_model(name)` — delete only when they say so
- `write(model, notes, length)` — a fresh passage from notes
- `continue(model, preceding_text, notes, length)` — the next passage
- `rewrite(model, text)` — same content, their voice
- `edit_span(model, text, start, end, replacement_draft)` — one bounded fix
- `score(model, text)` — style similarity and detector reading of the exact text
