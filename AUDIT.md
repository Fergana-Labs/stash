# Stash consistency audit — 2026-05-20

Cross-surface audit of the product: **UI vs CLI vs MCP vs Backend API vs Plugins vs Docs** plus a self-hosting verification pass.

**Source-of-truth ranking:** UI > CLI > everything else. When two surfaces disagree, the lower-ranked one is wrong unless there's a stated reason. Findings are categorized as **must-fix** (user-facing breakage), **should-fix** (drift that confuses but doesn't break), or **note** (design clarification only).

---

## Canonical concept list (from UI, locked)

**First-class nouns** (every other surface should use exactly these names, plural form for groups):

| Concept | Plural | Where it lives in UI |
|---|---|---|
| Workspace | Workspaces | sidebar switcher; `/workspaces/[id]` |
| Stash | Stashes | shareable bundles; `/stashes/[slug]`, sidebar group |
| Session | Sessions | agent transcripts; sidebar group |
| Files | Files | the workspace's virtual filesystem: nested folders containing pages (markdown/HTML docs) and uploads (blobs). One tree — `stash files tree` / `stash vfs ls /` / sidebar all see the same nodes. Pages and folders and uploads are *kinds of files*, not separate concepts. |
| Table | Tables | structured rows; `/tables/[id]` |

**Cross-cutting**: Activity (`/activity`), Discover (`/discover`), Search (`/search`), Trash (per-workspace), Comments (page-level), Integrations (GitHub / Google Drive / Notion / Obsidian).

**Verbs** (used in UI buttons + agent guidance): Quick Add, Import, Publish, Share, Fork, Pin.

Anything outside this list across other surfaces is either legacy, internal, or drift.

---

## Findings

### 🔴 MUST FIX — surfaces that ship broken commands today

#### F1. Plugin SessionStart hooks inject **dead commands**
Every plugin's `on_session_start.py` (and the per-plugin AGENTS.md / CLAUDE.md / GEMINI.md / stash.mdc files) tells the agent to use `stash history search`, `stash history query`, `stash history push`, `stash history agents`. **There is no `stash history` group** — `cli/main.py:2076` registers the group as `name="sessions"` (the variable is `hist_app` internally, but the public name is `sessions`).

Agents running any of these plugins will fail every "look stuff up" command on first try.

Real commands:
- `stash history search` → `stash sessions search`
- `stash history query`  → `stash sessions query`
- `stash history push`   → `stash sessions push`
- `stash history agents` → `stash sessions agents`

Files to fix (8):
- `plugins/claude-plugin/scripts/on_session_start.py` (CONTEXT string)
- `plugins/claude-plugin/README.md`
- `plugins/claude-plugin/CLAUDE.md`
- `plugins/codex-plugin/README.md`
- `plugins/codex-plugin/AGENTS.md`
- `plugins/cursor-plugin/README.md`
- `plugins/cursor-plugin/stash.mdc`
- `plugins/gemini-plugin/README.md`
- `plugins/gemini-plugin/GEMINI.md`
- `plugins/opencode-plugin/README.md`
- `plugins/opencode-plugin/AGENTS.md`

#### F2. Plugin hooks also reference `stash pages` (doesn't exist) and `stash notebooks` (doesn't exist)
- `plugins/claude-plugin/scripts/on_session_start.py:46` — `"stash pages --all"` should be `"stash files pages --all"`.
- The hard-coded SessionStart hook context (visible at the top of *this* conversation) lists `stash notebooks list --all` and `stash view <url>` — **neither exists**. Whoever owns the SessionStart text needs to strip these.

#### F3. `frontend/src/app/docs/cli` advertises **three commands that don't exist**
- `stash install`  — not a command. Real: `stash connect`.
- `stash enable`   — not a command. Real: `stash start`.
- `stash disable`  — not a command. Real: `stash stop`.

Section heading is "Streaming & hooks" (lines 85–93). These are the primary commands users land on after install — they must work.

#### F4. `frontend/src/app/docs/self-hosting` significantly understates the service set
The page lists **four containers** (postgres, backend, frontend, caddy). `docker-compose.prod.yml` actually starts **eight**: postgres, redis, backend, worker, beat, frontend, collab, caddy. Missing: `redis`, `worker`, `beat`, `collab`.

This is the public self-hosting guide. A new self-hoster will be surprised to see 4 extra containers and won't know what they're for. Need to add them with a one-line purpose each (Redis = Celery broker; worker = embeddings + extraction; beat = scheduled jobs; collab = Yjs WebSocket sidecar for page editing).

#### F5. `USE_CASES.md` advertises `stash curate` — not a command
`USE_CASES.md` cites `stash curate` (and `stash share <session_id>`, `stash connect` — those latter two are real). Either remove `stash curate` or rename to whichever command actually curates (today: `stash sessions push` for streaming; no batch-curate command exists).

#### F6. `ARCHITECTURE.md` references `permissions.py` router — doesn't exist
Strip the reference or replace with the real auth story (workspace-membership rows + Stash member-perm rows in `models.py`; no dedicated permissions router).

#### F7. `.env.example` is missing two env vars the backend actually reads
`backend/config.py` reads `INTEGRATIONS_ENCRYPTION_KEY` (line 78) and `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` / `ANTHROPIC_FAST_MODEL` (lines 101–103). None appear in `.env.example`. A self-hoster running `cp .env.example .env` will have integrations OAuth broken (encryption key required to store OAuth tokens) and "ask-the-stash" disabled.

This contradicts `README.md`'s claim "No LLM calls from the server." Either the README is stale (the server *does* make LLM calls for ask-the-stash / session summarization) or those features are hosted-only and the code path needs gating.

---

### 🟡 SHOULD FIX — drift that confuses but doesn't break

#### F8. MCP tool prefixing inconsistent
`cli/mcp_server.py` uses `stash_*` prefix for 41 of 44 tools. Three are unprefixed:
- `list_trash` (line 629)
- `restore_object` (line 637)
- `purge_object` (line 653)

Rename to `stash_list_trash`, `stash_restore` (or `stash_restore_object`), `stash_purge` (or `stash_purge_object`). MCP clients listing tools see these as out-of-family.

#### F9. CLI top-level vs grouped commands — overlap, not duplicates (resolved)
Initial reading flagged `stash share / publish / upload / browse / read` as duplicates of grouped forms. A second pass showed these are **semantically different**, not aliases:

| Top-level | Grouped form | Difference |
|---|---|---|
| `stash share` (session) | `stash sessions share` | Top-level auto-detects session + accepts `--file` attachments + adds a summary page. Grouped is bare transcript-only. |
| `stash publish` (local file) | `stash stashes publish` | Top-level creates a page+Stash from a local .html/.md file. Grouped changes an *existing* Stash's access level. Completely different. |
| `stash upload` | `stash files upload` | Top-level handles directory uploads + optional `--stash` bundling. Grouped is single-file only. |
| `stash browse` | — | No group equivalent. |
| `stash read` | — | No group equivalent. |

**Resolution: keep both, no changes.** The top-level forms exist for the muscle-memory verbs that match UI buttons; the grouped forms are the explicit / lower-level variants. Documenting the distinction is the docs/cli page's job (see F3 fix — the page now lists them separately under "Sessions", "Stashes", and "Uploaded files" sections).

#### F10. `concepts` page omits Stashes, Discover, Activity, and splits Files into three peers
`frontend/src/app/docs/concepts/page.tsx` previously listed six concepts: Workspace, Sessions, Files (badge "Pages"), Table, File (badge "Attachment"), Search. **Stashes were missing** — the eponymous concept of the product. The "Files / File" split also fragmented one concept into two, suggesting pages and uploads were separate things rather than two kinds of file in the same VFS.

**Resolution**: Concepts page now lists Workspace, Stash, Session, **Files** (the workspace's virtual filesystem — nested folders containing pages and uploads, all one tree visible via `stash files tree`, `stash vfs ls /`, and the sidebar), Table, plus cross-cutting Discover, Activity, Search. Pages, folders, and uploads are explicitly described as *kinds of files*, not separate concepts — matching the CLI's `stash files` umbrella and the sidebar's "Files" group.

#### F11. README install command still references the curl install
`README.md` Quick Start:
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"
```
Frontend docs/cli says `pip install stashai`. Frontend docs/quickstart says `pip install stashai && stash login`. Both work, but the install paths are diverging. Decide: is the canonical install `pipx`/`pip install stashai`, or the curl one-liner? Document one prominently, mention the other as fallback.

#### F12. `CHANGELOG.md` is functionally empty
Only 2 entries despite many shipped features (folders, tables, integrations, plugins, publish flow, vfs). Acceptable if v0 is the policy starting point — but say so in the file, or backfill.

---

### 🟢 NOTES — design decisions, not bugs

#### N1. `stash files` group correctly umbrellas folders + pages + files
Confirmed intentional. Not a finding.

#### N2. MCP capability gaps (subset of CLI) — mostly intentional
MCP doesn't ship: `discover_search_public`, `invite_accept`, `session_import_jsonl`, `signin`/`connect`/`start`/`stop`/`welcome`/`config`. The latter group is correctly CLI-only (local state / streaming control / auth). The former three are arguable gaps; defer unless an agent reports needing them.

#### N3. Plugin endpoint config is *consistent* via `~/.stash/config.json`
All plugins resolve the endpoint by:
1. Reading `~/.stash/config.json`'s `base_url` (set by `stash login`/`stash signin`)
2. Optional plugin-side override (Claude has `api_endpoint` via Claude Code's `userConfig`; others piggyback on the CLI config)
3. Env vars `STASH_URL` and `STASH_API_KEY` override config

For self-hosters, the single instruction is: `stash signin <your_stash_url>` after install. All plugins inherit. Document this once in self-hosting page; don't try to "align" per-plugin env vars.

#### N4. Plugin version policy
Claude plugin is pinned at `0.1.83`; others float on the latest `stashai` package. This is fine — Claude Code's plugin system uses the version. Just call it out so we don't bump only Claude and miss the others.

---

## Self-host runbook + verification plan

See `Phase 3` below. Verification log will be appended as it runs.

## Fixes — files & order

Ordered by user impact. (Detailed task list in TaskCreate.)

1. **`frontend/src/app/docs/cli/page.tsx`** — replace `install`/`enable`/`disable` → `connect`/`start`/`stop` (F3).
2. **`frontend/src/app/docs/self-hosting/page.tsx`** — add redis/worker/beat/collab containers; add `INTEGRATIONS_ENCRYPTION_KEY` to the env var table (F4, F7).
3. **`frontend/src/app/docs/concepts/page.tsx`** — add Stashes, Folders; clean up Files/File confusion (F10).
4. **`.env.example`** — add `INTEGRATIONS_ENCRYPTION_KEY`, gate `ANTHROPIC_API_KEY` behind a "managed/ask-the-stash" section (F7).
5. **All plugin SessionStart scripts + READMEs** — `history` → `sessions`, `stash pages` → `stash files pages` (F1, F2).
6. **`README.md`, `USE_CASES.md`, `ARCHITECTURE.md`** — strip dead commands/routers, align with UI concepts (F5, F6, F11, F12).
7. **`cli/mcp_server.py`** — rename `list_trash`/`restore_object`/`purge_object` with `stash_` prefix (F8).
8. **`cli/main.py`** — add "Alias of X" to top-level command help where duplicated (F9).

---

## Self-host verification log

Ran from the worktree (`/Users/samzliu/code/moltchat-audit`) with a port-remapped override (`docker-compose.audit.yml`) so the audit stack runs alongside the user's existing dev postgres/redis without conflict.

### Stack boot

```
docker compose -f docker-compose.yml -f docker-compose.audit.yml up -d --build
```

All 8 containers came up healthy on first boot:

| Service | Image | Port (host) | Status |
|---|---|---|---|
| postgres | pgvector/pgvector:pg16 | 5444 | healthy |
| redis | redis:7-alpine | 6399 | healthy |
| backend | (built) | 3466 | healthy |
| worker | (built) | — | up |
| beat | (built) | — | up |
| collab | (built) | 3488 | up |
| frontend | (built) | 3477 | up |
| | | | |

Migrations ran automatically on backend startup. `GET /health` → `{"status":"ok"}`.

### Golden path

| Step | Surface | Result |
|---|---|---|
| Register user | `POST /api/v1/users/register` | ✅ 201, API key returned |
| Create workspace | `POST /api/v1/workspaces` | ✅ workspace ID + invite code |
| Push session event | `POST /api/v1/workspaces/{id}/sessions/events` | ✅ event row |
| Create page | `POST /api/v1/workspaces/{id}/pages/new` | ✅ page ID |
| List pages | `GET /api/v1/workspaces/{id}/pages` | ✅ shows created page |
| Create stash bundling the page | `POST /api/v1/workspaces/{id}/stashes` | ✅ stash with slug `audit-smoke-stash-fvcutq` |
| Make stash public + discoverable | `PATCH /api/v1/stashes/{id}` | ✅ access=public |
| Fetch public stash by slug (API) | `GET /api/v1/stashes/{slug}` | ✅ 200, JSON payload |
| **Public stash page (frontend, signed-out)** | `GET /stashes/{slug}` | ❌ → ✅ **after self-host fix below** |
| Docs pages render new content | `GET /docs/{concepts,cli,self-hosting}` | ✅ all 200; updated content visible (Stash + Folders + Discover concepts, `stash connect/start/stop`, redis/worker/beat/collab + INTEGRATIONS_ENCRYPTION_KEY/ANTHROPIC_API_KEY env vars) |

### CLI verification

Pointed the installed `stash` CLI at the self-hosted backend via env vars:

```
STASH_URL=http://localhost:3466 STASH_API_KEY=<key> stash whoami       # ✅
STASH_URL=http://localhost:3466 STASH_API_KEY=<key> stash workspaces list   # ✅
STASH_URL=http://localhost:3466 STASH_API_KEY=<key> stash sessions push "…"  # ✅
STASH_URL=http://localhost:3466 STASH_API_KEY=<key> stash sessions search "…"  # ✅ full-text + rank
STASH_URL=http://localhost:3466 STASH_API_KEY=<key> stash files pages         # ✅ lists created page
```

The renamed `stash sessions *` group (replacing dead `stash history *`) is the canonical path and works end-to-end against the self-hosted backend.

---

## 🔴 BONUS FINDING — uncovered during Phase 3 boot

### F13. Frontend SSR + rewrites use the *public* API URL inside the container
Self-host boot exposed a real runtime bug. The public `/stashes/{slug}` page returned **500** on first boot because:

- `frontend/next.config.ts` `rewrites()` used `process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456"` for proxy destinations. Inside the frontend container `localhost:3456` is the frontend itself — `ECONNREFUSED`.
- Three server-component pages (`(app)/stashes/[slug]/page.tsx`, `.../embed/page.tsx`, `.../items/[type]/[id]/page.tsx`) hard-coded the same fallback.
- `docker-compose.prod.yml` set `NEXT_PUBLIC_API_URL=${PUBLIC_URL}` — fine for the browser, broken for SSR (would loop through Caddy back into the container).

**Fix applied** (all in this PR):
1. New `frontend/src/lib/backendOrigin.ts` exports `SSR_BACKEND_ORIGIN` preferring `BACKEND_INTERNAL_URL` → `NEXT_PUBLIC_API_URL` → `localhost:3456`.
2. `next.config.ts` does the same lookup for rewrite destinations.
3. The 3 SSR pages now import `SSR_BACKEND_ORIGIN`.
4. `frontend/Dockerfile` adds `BACKEND_INTERNAL_URL` as an `ARG/ENV` (required at build time — `rewrites()` is evaluated by `next build`).
5. `docker-compose.yml`, `docker-compose.prod.yml`, and `docker-compose.audit.yml` set `BACKEND_INTERNAL_URL=http://backend:3456` for the frontend service (both as build arg and runtime env).

**Re-verified**: with the fix, `GET /stashes/audit-smoke-stash-fvcutq` returns 200 + "Audit smoke stash" + "Hello from the audit" in the rendered HTML. JSON content-negotiation `Accept: application/json` also returns the stash payload directly.

Without this fix, every self-hoster's public Stash URLs would 500 — and the `/discover` fork flow would silently fail at SSR. This is the most important bug surfaced by the audit.

