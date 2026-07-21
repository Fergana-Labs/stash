Write extremely easy to consume code. Optimize for readability: skimmable, no cleverness, early returns.

> This file is the single source of truth for agent rules in this repo. `AGENTS.md` is a symlink to this file so Codex, OpenCode, and any other AGENTS.md-style tool get the same instructions as Claude Code. Edit this file; never edit AGENTS.md directly.

### Write simple code
We are a startup. Therefore, code simplicity is our most important concern. Please NEVER
 - Add backwards compatibility support of any kind. This includes compatibility shims, aliases, legacy format support, and fallback code paths.
 - Attempt to preserve backwards compatibility when making an edit.
 - Use fallbacks of ANY kind, ANYWHERE, under ANY circumstance. There are no exceptions. This includes UX-saving fallbacks when a primary path fails, default values papered over a missing input (`x or DEFAULT`, `x or stored_value()`), `try/except` that swallows an error and continues, and "if the real source is empty, use this other source" chains. When a required input is absent or a path fails, FAIL LOUD (raise/exit with a clear message) — never silently substitute. A single source of truth with one codepath, always.
 - Support old formats. If a format changes, change it everywhere in one shot.

**Data migrations are allowed** (updated 2026-07: we have real users now). When a schema or format changes, you may — and should — write a one-time migration that carries existing user data forward to the new format, so nobody loses data. This is not a license for backwards compatibility: migrate the data forward in one shot, then delete the old path. The end state is still a single format and one codepath — the migration is just how you get there without stranding what users already have. Everything else above stands: no compatibility shims, no fallbacks, no dual code paths.

Here are some common code patterns that we need you to avoid:
 - Excessive try/catch: only use try/catch when there's a reasonable expectation that the code within might fail during normal usage. Every try/catch that we add adds another codepath that we need to maintain (the catch) and balloons complexity. In general, we follow the concept of "parse, don't validate" from TDD whenever possible. That is, we validate inputs at module boundaries, and within a module, we don't randomly add try/catch everywhere.

 - Unhelpful comments that reiterate what the code does: The point of a comment is to explain information that is not obvious from reading the code. A good rule of thumb: if your comment is an action (eg: sets the diff viewer open state), it is probably a bad comment. If it is a description (eg: the diff viewer state must be synced to our ui interaction server) it is likely a good comment.

### Be self-sufficient
If you are about to ask the user to do something for you, think about whether you can do it yourself.

- **Never ask the user to check logs.** Check them yourself — via running the server with captured output, MCPs for hosted servers, or ngrok inspector (`localhost:4040`).
- **Never speculate about env vars, API keys, or config.** If you need to know whether something is set, check it yourself (e.g. `env | grep`, read `.env`, etc.). Just do it. Do not guess or assume. Do not ask the user. Check it yourself.
- **Never ask the user to test UI**. Use `agent-browser` as the default tool for manual E2E/QA browser checks: click through the changed workflow, inspect the page state, capture screenshots when useful, and check logs yourself. Use existing Playwright tests for scripted regression coverage when the repo already has them or when adding a durable test is part of the task.
- **Never ask permission to kill/restart local processes.** If you need to restart uvicorn, ngrok, or any dev server to make progress, just do it. But scope kills to this worktree: several worktrees run the same stack on this machine, so kill by specific PID or port (`kill <pid>`, `pkill -f "next dev -p 3457"`) — never by bare command pattern (`pkill -f "next dev"`, `pkill -f uvicorn`), which takes down other worktrees' servers.


### PR hygiene

When opening or updating a PR that includes GUI changes, always add product screenshots to the PR description or PR thread. Capture the changed user-facing screens yourself, and include admin/configuration screens too when they are part of the workflow.
Never commit screenshots, recordings, or other assets that exist only to support a PR description or review thread. Keep those files outside the repo or delete them before staging, then attach/upload them directly to the PR instead.

<!-- stash-context -->
## Stash

This repo uses [Stash](https://joinstash.ai) for your agent Sessions and Files.
Your coding agent has the `stash` CLI on its PATH. Run `stash --help` to see commands.

### What a Skill is

A Skill is a *special folder* — one containing a SKILL.md — holding related artifacts (pages, files, tables) that shares like any folder and gains a public URL when published. Reach for one when you're publishing a *collection* of related things together — a project writeup with its supporting files, a research thread with its sources, a session transcript plus the files it produced.

A Skill is **not** a wrapper to slap on every single file you happen to share. One-item Skills clutter Discover and defeat the model. Pick the right tool:

- Share a single file or a folder/project → `stash upload <path> --json`, hand over `app_url` (no Skill).
- Publishing a curated bundle → `stash upload <path> --skill "<title>" --json`.
- Creating a fresh skill → `stash skills create "<name>" --public --json`.
- Share a coding session → `stash share <session_id>`.

Run `stash prompts agent-guidance` to reprint this guidance mid-session.

Common reads:
- `stash search "<query>" --json` — full-text search across files, sessions, and connected sources
- `stash vfs "ls /"` — browse your Stash as a filesystem: files, sessions, tables, skills, sources
- `stash vfs "cat '/files/<page>.md'"` — read any page, file, transcript, or source doc
- `stash sessions agents` — who's been active

Browsing and reading your Stash content (files, pages, sessions, tables, skills, connected sources) is
done through the VFS — `stash vfs "<bash>"` (ls/cat/find/grep/tree) — not dedicated read subcommands.

### LLM configuration (server-side)

All LLM calls happen server-side; the plugin never calls Anthropic — it only
uploads transcripts. Ask-the-stash runs a direct Anthropic tool-use loop
(`backend/services/tool_loop.py` — the SDK subprocess runner was deliberately
abandoned; rationale in that file's docstring), and the cloud agent runs
harness CLIs on Fly Sprites.

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
- Seed dev data: `python -m backend.scripts.seed_dev` — a demo user + one fake connected source per provider (bypasses OAuth), so the integrations UI, source sharing, and the VFS `/sources` tree are demoable locally. Prints an API key; set it with `localStorage.setItem('stash_token', '<key>')` in the browser console. Refuses to run under Auth0.
- Tests: `pytest`
- Lint (matches CI exactly): `ruff check backend/ cli/ && ruff format --check backend/ cli/`
  - Fix formatting with `ruff format backend/ cli/`. There is no black; ruff is the only linter *and* formatter.

### Frontend (`frontend/`)
- Install: `cd frontend && npm ci`
- Dev: `cd frontend && npm run dev` (port 3457)
- Build: `cd frontend && npm run build`
- Tests: `cd frontend && npm test` (vitest)
- Lint: `cd frontend && npm run lint`
- There is no E2E suite (no playwright config or specs exist); frontend tests are vitest only.

### Frontend conventions
Enforced on every frontend change — new code and any code you touch.

- **No route magic strings.** Use `routes` from `src/lib/workspace-routes.ts` (`routes.page(id)`, etc.) or `skillItemPath` from `src/lib/localSkill.ts`. Missing a route? Add it to `routes` first.
- **No magic numbers/strings.** If a literal repeats or encodes a domain concept, name it as a constant.
- **Don't repeat patterns.** Check `src/lib/` and `src/components/ui/` before writing a new helper/component. Copy-paste across files = extract it.

### Landing page (`www/`)
- Install: `cd www && npm ci`
- Dev: `cd www && npm run dev` (port 3100)
- Build: `cd www && npm run build`
- Lint: `cd www && npm run lint`

### Local stack
- One-shot start (db + redis + backend + celery + collab + frontend): `./start.sh`
- App ports are fixed and exclusive per machine: backend 3456, frontend 3457, collab 3458. OAuth redirect URIs are registered against 3456, so there is no way to run the stack on other ports. If a port is taken, `start.sh` fails and prints the holding process: one local stack at a time — kill the holder only if it's yours or a zombie, otherwise wait. Tests, lint, and most dev work don't need the live stack.
- There is no dev docker compose. `./start.sh` is the only local dev path; `docker-compose.prod.yml` is for self-hosters only.

### Deployment (hosted prod — joinstash.ai)
**Merging to `main` deploys to production. There is no separate release step for the hosted app.**

- Hosted prod runs on **Render** (team `Stash`, region oregon), building directly from this repo's Dockerfiles. Every service has `autoDeploy: yes` on `branch: main`, so a commit to `main` triggers a build + deploy within a couple of minutes. Confirm/inspect via the Render MCP (`list_services`, `list_deploys`, `list_logs`) — do not infer deploy state from repo files.
- Services (all `Fergana-Labs/stash`, branch `main`): `stash_backend` (slug `moltchat`, → api.joinstash.ai, `backend/Dockerfile`), `stash_app_frontend`, `stash_collab`, `stash-celery-worker`, `stash-celery-beat`. `aspose-pptx` is the one service defined in `render.yaml`; the rest are configured in the Render dashboard, so the repo holds no blueprint for them.
- **Migrations run automatically at backend boot** (`backend/database.py` runs `alembic upgrade head`), so a merged migration applies to the prod DB on the next deploy — no manual `alembic` step.
- Prod DB is **Neon** (`stash-prod`, id `little-scene-08473932`), not Render Postgres. Query read-only via the Neon MCP.
- `docker-compose.prod.yml` and the **GHCR images are for self-hosters only** — they are NOT how joinstash.ai deploys. Editing them does not affect prod.
- `publish.yml` (on push to `main`) publishes the **`stashai` CLI to PyPI** on a version bump and builds GHCR release images — this is CLI/self-host distribution, separate from the Render app deploy.

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
