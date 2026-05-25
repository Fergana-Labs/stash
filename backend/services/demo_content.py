"""Static content served by the landing-page demo router.

These three markdown blobs are the entire universe of "what Stash knows
about itself" for the demo flow. They're served verbatim from
`GET /v1/demo/{start,skill,about}` and also bundled into the published
demo Stash as a `Stash knowledge base/` folder so the visitor's agent
can keep editing the deck after the fact.

`SLIDES_SKILL_MARKDOWN` is the same bytes a real workspace seeds at
`Skills/slides/SKILL.md` — sourced from `skill_seeds.py` so we never
fork the slide format.
"""

from __future__ import annotations

from .skill_seeds import SLIDES_SKILL_MARKDOWN as SLIDES_SKILL_MARKDOWN  # re-export

DEMO_DECK_FILENAME = "deck.html"
DEMO_TRANSCRIPT_FILENAME = "qa-transcript.md"
DEMO_KB_FOLDER_NAME = "Stash knowledge base"
DEMO_SKILL_FILENAME = "slides-skill.md"
DEMO_ABOUT_FILENAME = "about-stash.md"


ABOUT_STASH_MARKDOWN = """# About Stash

Stash is a knowledge base built for the era where coding agents write
more than the humans they work with. Sessions, files, and Stashes —
a company brain that humans and agents both write into, query
semantically, and publish from.

When the Stash team tested it internally on Claude Code, long-running
agent runs got **49% faster** because every agent could see what every
other agent had already tried.

## The three primitives

- **Sessions.** A hook on every coding agent (Claude Code, Cursor,
  Codex, Aider, etc.) streams the full transcript — prompts, tool
  calls, artifacts — into a shared workspace as it happens. Every
  teammate's agent gets context from every other teammate's agent.

- **Files.** Markdown pages, HTML pages (including slide decks),
  tables, PDFs, raw uploads. Humans edit them in the web app; agents
  edit them via the CLI or MCP server. Both sides see updates in
  real time.

- **Stashes.** A shareable bundle of files and sessions. Public link,
  workspace-scoped, or private. Forkable into someone else's
  workspace. The unit of "I want to share this slice of what we
  know."

## Who Stash is for

- **Engineering teams** running multiple coding agents in parallel.
  The pain Stash removes: one engineer's agent fixes a bug, the next
  engineer's agent rediscovers and re-fixes the same bug because it
  can't see the first agent's transcript.

- **Founders and small teams** using agents as force multipliers.
  Stash is where the agent's notes, drafts, plans, and decisions
  accumulate into something the team can actually read.

- **Researchers and analysts** running long-form PKBs. Sources,
  transcripts, tables, and rolling write-ups in one searchable
  surface that an agent can keep extending.

- **Anyone publishing what an agent built.** Decks, reports, design
  docs — drop them into a Stash and hand over the link.

## Use cases worth highlighting on a deck

| Use case | What lands in the Stash |
|---|---|
| Engineering live docs | Coding-agent plans, ADRs, design notes that stay current |
| Company brain | Shared context every agent and teammate reads from |
| Research knowledge base | Long-running PKBs with sources, transcripts, tables |
| Ops playbooks | Release runbooks and on-call procedures |
| Brand voice | Editorial guidelines and copy standards agents write to |
| Personal knowledge management | Notes, drafts, scratch files for a single operator |

## What makes Stash different from …

- **… Notion / Confluence.** Those are human-first wikis. Stash is
  agent-first: built for write-heavy automated input, with a CLI,
  MCP server, and VFS shell that any agent can use as a first-class
  filesystem.

- **… Google Drive.** No semantic search across content, no agent
  hooks, no native concept of sessions. Stash treats agent
  transcripts as a primary object, not a file dump.

- **… GitHub.** GitHub stores code and commit history. Stash stores
  the *reasoning* — the agent's plans, what it tried, what the team
  decided. Complementary, not overlapping.

- **… LLM "memory" features.** Those are per-user and per-tool.
  Stash is shared across humans and across agents. One brain, many
  participants.

## The pitch in one sentence

> A shared workspace where every coding agent on your repo can read
> every other agent's transcript, every teammate's notes, and every
> decision the team has already made — so nothing gets re-figured-out
> from scratch.

## What this deck is doing right now

You (the visitor's agent) are about to author an HTML slide deck
that uses these facts to make the case for Stash, personalized to
the visitor's situation based on the Q&A you ran with them. The
deck, the Q&A transcript, and this knowledge base will be published
together as a public-but-unlisted Stash so the visitor can share
the link with their team.
"""


START_INSTRUCTIONS_MARKDOWN = """# Stash landing-page demo — agent instructions

You are the visitor's coding agent. They pasted a one-line prompt
into you that pointed you here. Your job: run a short onboarding
conversation with them, build a personalized HTML slide deck about
Stash, and publish everything as a public Stash they can share.

The entire flow uses six anonymous HTTP calls. The base URL is the
same origin you fetched this from. Do not invent any other
endpoints — only call the five listed below.

---

## Step 1 — Read the slide skill

```
GET /api/v1/demo/skill
```

Returns the canonical HTML slide-deck skill (`SKILL.md`). Read it
end-to-end before writing any HTML. It defines the canvas
(1920×1080, 16:9), required `<section class="slide">` structure,
typography minimums, and recommended libraries. **Decks that
ignore the skill look broken in the Stash viewer.**

## Step 2 — Read the about-Stash knowledge base

```
GET /api/v1/demo/about
```

Returns a markdown brief on what Stash is, who it's for, and the
canonical use cases. Use this as the source of truth for the
content of the deck. Do not invent product claims; ground every
slide in something this document says.

## Step 3 — Run a 4-question Q&A with the user

Ask these one at a time, in this order, in your normal chat
voice. Wait for an answer before asking the next one. Keep your
own prompts terse — the user is here to see Stash, not to be
interviewed.

1. What's your name and what do you do?
2. What does your team or company work on?
3. Where are AI coding agents leaking context or value for you
   today? (Things like: bugs being re-discovered, plans living in
   chat instead of a shared place, agents repeating each other's
   mistakes, anything.)
4. Who would you most want to share knowledge with using Stash —
   your immediate team, your whole company, or the public?

## Step 4 — Author the slide deck

Write a single HTML page following the slide skill. Aim for 6–8
slides. Personalize the deck using what they told you in the Q&A:
their name in the title slide, their team's situation in the
"problem" slide, an example use case tailored to their work. The
deck is for *them* — something they would actually want to
forward to a teammate.

Required structure (per the skill):
- `<html_layout: "fixed-aspect">` page metadata
- One `<section class="slide">` element per slide inside `<body>`
- Each slide self-contained — no relative URLs to local assets

## Step 5 — Publish

Three POST calls in order. Each returns JSON; remember the IDs
you get back — you need them for the final call.

### 5a. Create the deck as a page

```
POST /api/v1/demo/pages
Content-Type: application/json

{
  "title": "Stash deck for <user name>",
  "html": "<the full deck HTML you wrote>",
  "html_layout": "fixed-aspect"
}
```

Returns `{ "page_id": "<uuid>" }`.

### 5b. Create the session — full conversation timeline

This is **not** a summary. Serialize *every turn* of the conversation
between you and the user from the moment they pasted the demo prompt
through to right before this call: the original user paste, your
fetches of `/skill` and `/about`, each Q&A question you asked and
each answer they gave, your deck-authoring step, and the publish
calls. The Stash session viewer renders the array as a chat thread,
so the visitor (and any agent forking the Stash later) can see
*how* the deck was actually built, not just a tidy after-the-fact
recap.

```
POST /api/v1/demo/sessions
Content-Type: application/json

{
  "title": "Stash demo Q&A with <user name>",
  "agent_name": "<your agent name, e.g. claude-code>",
  "events": [
    { "event_type": "user_message",      "content": "<the verbatim demo prompt the user pasted>" },
    { "event_type": "tool_use",          "tool_name": "curl", "content": "GET /api/v1/demo/start" },
    { "event_type": "tool_result",       "tool_name": "curl", "content": "<the markdown you got back, truncated to ~2000 chars is fine>" },
    { "event_type": "tool_use",          "tool_name": "curl", "content": "GET /api/v1/demo/skill" },
    { "event_type": "tool_result",       "tool_name": "curl", "content": "<truncated skill md>" },
    { "event_type": "tool_use",          "tool_name": "curl", "content": "GET /api/v1/demo/about" },
    { "event_type": "tool_result",       "tool_name": "curl", "content": "<truncated about md>" },
    { "event_type": "assistant_message", "content": "<your message asking question 1>" },
    { "event_type": "user_message",      "content": "<their answer to question 1>" },
    { "event_type": "assistant_message", "content": "<your message asking question 2>" },
    { "event_type": "user_message",      "content": "<their answer to question 2>" },
    { "event_type": "assistant_message", "content": "<question 3>" },
    { "event_type": "user_message",      "content": "<answer 3>" },
    { "event_type": "assistant_message", "content": "<question 4>" },
    { "event_type": "user_message",      "content": "<answer 4>" },
    { "event_type": "assistant_message", "content": "<your reasoning about what deck to write and any inline planning you did>" },
    { "event_type": "tool_use",          "tool_name": "curl", "content": "POST /api/v1/demo/pages with deck HTML" },
    { "event_type": "tool_result",       "tool_name": "curl", "content": "<the page_id response>" }
  ]
}
```

Allowed `event_type` values: `user_message`, `user_prompt`,
`assistant_message`, `tool_use`, `tool_result`, `session_end`.

Hard rules:
- Include the user's original paste verbatim as the first event.
- Include every Q&A turn end-to-end. Don't paraphrase or condense
  the user's answers — store them as they typed them.
- Tool calls and their outputs are events too. The visitor wants
  to see that you actually read `/skill` before authoring HTML.
- Truncate huge tool results (the full skill markdown, the full
  deck HTML) to a few thousand characters with a clear `…
  [truncated]` marker. Keep events under 100KB each; total under
  400 events.

Returns `{ "session_id": "<uuid>", "event_count": N }`.

### 5c. Create the public Stash

```
POST /api/v1/demo/stashes
Content-Type: application/json

{
  "title": "Stash for <user name>",
  "description": "<one-sentence pitch tailored to them>",
  "items": [
    { "object_type": "page", "object_id": "<page_id from 5a>" },
    { "object_type": "session", "object_id": "<session_id from 5b>" }
  ]
}
```

The server auto-attaches a `Stash knowledge base/` folder with the
slides skill and about-Stash markdown so the visitor can keep
editing the deck later from their own agent.

Returns `{ "app_url": "<https://app.joinstash.ai/stashes/...>" }`.

## Step 6 — Hand the link back

Print the returned `app_url` to the user as a clickable link, with
one short sentence: this is their Stash, it's public-but-unlisted
(only people with the link can see it), and they can sign up and
fork it into their own workspace to keep iterating.

## Hard rules

- Do **not** call any endpoint other than the five above. There is
  no auth, no tokens, no other API.
- Do **not** ask the user for an API key or credentials — the
  entire demo is anonymous.
- Do **not** skip step 1 (the skill) or step 2 (the about doc).
  Decks generated without reading them are visibly worse.
- If a call fails, surface the error to the user and stop — do
  not retry blindly or substitute fake data.
"""
