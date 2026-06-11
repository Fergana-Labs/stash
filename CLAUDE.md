Write extremely easy to consume code. Optimize for readability: skimmable, no cleverness, early returns.

> This file is the single source of truth for agent rules in this repo. `AGENTS.md` is a symlink to this file so Codex, OpenCode, and any other AGENTS.md-style tool get the same instructions as Claude Code. Edit this file; never edit AGENTS.md directly.

### Write simple code
We are a startup. Therefore, code simplicity is our most important concern. Please NEVER
 - Add backwards compatibility support of any kind. This includes migrations, compatibility shims, aliases, legacy format support, and fallback code paths.
 - Attempt to preserve backwards compatibility when making an edit.
 - Use fallbacks to save the UX when a primary path doesn't work (we'd rather fail fast, and this helps us to maintain as few codepaths as possible)
 - Support old formats. If a format changes, change it everywhere in one shot.

Here are some common code patterns that we need you to avoid:
 - Excessive try/catch: only use try/catch when there's a reasonable expectation that the code within might fail during normal usage. Every try/catch that we add adds another codepath that we need to maintain (the catch) and balloons complexity. In general, we follow the concept of "parse, don't validate" from TDD whenever possible. That is, we validate inputs at module boundaries, and within a module, we don't randomly add try/catch everywhere.

 - Unhelpful comments that reiterate what the code does: The point of a comment is to explain information that is not obvious from reading the code. A good rule of thumb: if your comment is an action (eg: sets the diff viewer open state), it is probably a bad comment. If it is a description (eg: the diff viewer state must be synced to our ui interaction server) it is likely a good comment.

### Be self-sufficient
If you are about to ask the user to do something for you, think about whether you can do it yourself.

- **Never ask the user to check logs.** Check them yourself — via running the server with captured output, MCPs for hosted servers, or ngrok inspector (`localhost:4040`).
- **Never ask permission to kill/restart local processes.** If you need to restart uvicorn, ngrok, or any dev server to make progress, just do it.
- **Never speculate about env vars, API keys, or config.** If you need to know whether something is set, check it yourself (e.g. `env | grep`, read `.env`, etc.). Just do it. Do not guess or assume. Do not ask the user. Check it yourself.
- **Never ask the user to test UI**. Use `agent-browser` as the default tool for manual E2E/QA browser checks: click through the changed workflow, inspect the page state, capture screenshots when useful, and check logs yourself. Use existing Playwright tests for scripted regression coverage when the repo already has them or when adding a durable test is part of the task.

### Past Conversation Context

Previous Claude coding sessions are stored as `.jsonl` files in your `~/.claude` directory. Read these to understand prior decisions, debugging sessions, and context that isn't in git history.

When you create or update a PR, share the GitHub link with the user at the end of your session.
When you make local changes for a task, commit them, push the branch, and open a ready-for-review PR before finishing unless the user explicitly says not to. Do not open draft PRs unless the user explicitly asks for a draft.
When making local changes for a task that already has a PR, commit and push those changes to the PR branch before finishing so the remote branch stays up to date.

### PR hygiene

When opening or updating a PR that includes GUI changes, always add product screenshots to the PR description or PR thread. Capture the changed user-facing screens yourself, and include admin/configuration screens too when they are part of the workflow.
Never commit screenshots, recordings, or other assets that exist only to support a PR description or review thread. Keep those files outside the repo or delete them before staging, then attach/upload them directly to the PR instead.

<!-- stash-context -->
## Stash

This repo uses [Stash](https://joinstash.ai) for shared agent Sessions and Files.
Your coding agent has the `stash` CLI on its PATH. Run `stash --help` to see commands.

### What a Stash is

A Stash is a *named, curated bundle of related artifacts* (pages, files, sessions, tables) with its own access control and an optional public URL. Reach for one when you're publishing a *collection* of related things together — a project writeup with its supporting files, a research thread with its sources, a session transcript plus the files it produced.

A Stash is **not** a wrapper to slap on every single file you happen to share. One-item Stashes clutter Discover and defeat the model. Pick the right tool:

- Internal share of a single file → `stash files upload <path> --json`, hand over `app_url`.
- Upload a folder/project → `stash upload <path> --json` (returns `app_url`, no Stash).
- Publishing a curated bundle → `stash upload <path> --stash "<title>" --json`.
- Composing from existing items → `stash stashes create "<title>" --items '<json>' --json`.
- Share a coding session → `stash share <session_id>`.

Run `stash prompts agent-guidance` to reprint this guidance mid-session.

Common reads (all support `--json`):
- `stash sessions search "<query>"` — full-text search across transcripts
- `stash sessions query --limit 20` — latest session events
- `stash sessions agents` — who's been active
- `stash files tree` — browse workspace Files

### LLM configuration (server-side)

All LLM calls go through the backend via the Claude Agent SDK
(`claude-agent-sdk`). The plugin no longer makes Anthropic calls; it
only uploads transcripts.

Two model tiers, configured in `backend/.env`:
- `ANTHROPIC_API_KEY` — required for ask-the-stash.
- `ANTHROPIC_MODEL` — quality tier (default `claude-sonnet-4-6`). Used by
  ask-the-stash.
- `ANTHROPIC_FAST_MODEL` — fast tier (default `claude-haiku-4-5`).

## Project layout

- `backend/` — FastAPI app (Python 3.12), runs on port `3456`. Migrations via Alembic.
- `frontend/` — Next.js app (the product UI), runs on port `3457`.
- `www/` — Next.js landing page, runs on port `3100`.

## Commands

### Developing the stash CLI
By default `stash` is the released PyPI build (`uv tool` install, self-updating). To develop against this checkout's code instead:
1. Once per checkout: `uv venv -p 3.12 && uv pip install -e .`
2. Per terminal: `source .venv/bin/activate` — your prompt shows `(.venv)` and `stash` now runs this checkout's working tree. New terminals default back to the released CLI.

### Backend
- Install deps: `uv pip install -r backend/requirements.txt -r backend/requirements-dev.txt`
- Migrate DB: `alembic upgrade head`
- Run server: `uvicorn backend.main:app --host 0.0.0.0 --port 3456 --proxy-headers --forwarded-allow-ips '*'`
- Tests: `pytest`
- Lint: `ruff check .`

### Frontend (`frontend/`)
- Install: `cd frontend && npm ci`
- Dev: `cd frontend && npm run dev` (port 3457)
- Build: `cd frontend && npm run build`
- Tests: `cd frontend && npm test` (vitest)
- Lint: `cd frontend && npm run lint`
- E2E: `cd frontend && npx playwright test` (requires `npx playwright install chromium` once)

### Landing page (`www/`)
- Install: `cd www && npm ci`
- Dev: `cd www && npm run dev` (port 3100)
- Build: `cd www && npm run build`
- Lint: `cd www && npm run lint`

### Local stack
- One-shot start (migrations + backend + frontend): `./start.sh`
- Docker compose: `docker compose up`

# 12-rule template

These rules apply to every task in this project unless explicitly overridden.
Bias: caution over speed on non-trivial work. Use judgment on trivial tasks.

## Rule 1 — Think Before Coding
State assumptions explicitly. If uncertain, ask rather than guess.
Present multiple interpretations when ambiguity exists.
Push back when a simpler approach exists.
Stop when confused. Name what's unclear.

## Rule 2 — Simplicity First
Minimum code that solves the problem. Nothing speculative.
No features beyond what was asked. No abstractions for single-use code.
Test: would a senior engineer say this is overcomplicated? If yes, simplify.

## Rule 3 — Surgical Changes
Touch only what you must. Clean up only your own mess.
Don't "improve" adjacent code, comments, or formatting.
Don't refactor what isn't broken. Match existing style.

## Rule 4 — Goal-Driven Execution
Define success criteria. Loop until verified.
Don't follow steps. Define success and iterate.
Strong success criteria let you loop independently.

## Rule 5 — Use the model only for judgment calls
Use me for: classification, drafting, summarization, extraction.
Do NOT use me for: routing, retries, deterministic transforms.
If code can answer, code answers.

## Rule 6 — Token budgets are not advisory
Per-task: 4,000 tokens. Per-session: 30,000 tokens.
If approaching budget, summarize and start fresh.
Surface the breach. Do not silently overrun.

## Rule 7 — Surface conflicts, don't average them
If two patterns contradict, pick one (more recent / more tested).
Explain why. Flag the other for cleanup.
Don't blend conflicting patterns.

## Rule 8 — Read before you write
Before adding code, read exports, immediate callers, shared utilities.
"Looks orthogonal" is dangerous. If unsure why code is structured a way, ask.

## Rule 9 — Tests verify intent, not just behavior
Tests must encode WHY behavior matters, not just WHAT it does.
A test that can't fail when business logic changes is wrong.

## Rule 10 — Checkpoint after every significant step
Summarize what was done, what's verified, what's left.
Don't continue from a state you can't describe back.
If you lose track, stop and restate.

## Rule 11 — Match the codebase's conventions, even if you disagree
Conformance > taste inside the codebase.
If you genuinely think a convention is harmful, surface it. Don't fork silently.

## Rule 12 — Fail loud
"Completed" is wrong if anything was skipped silently.
"Tests pass" is wrong if any were skipped.
Default to surfacing uncertainty, not hiding it.
