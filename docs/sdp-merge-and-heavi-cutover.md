# SDP merge runbook + Heavi cutover plan

Written 2026-08-21 late evening, at the end of the session that prepared
PR #1075 (`pm-time-two`) for merge. Read this before merging, babysitting
the deploy, or starting the Heavi cutover.

## State of the world

- **PR #1075** is APPROVED and MERGEABLE. Local suites at head `4afa4bda`:
  backend 1422 + CLI 259 + frontend 302, ruff clean, single migration
  head 0197. Confirm CI is green on the actual head before merging.
- **Merging fires three things at once**: the prod deploy (Render,
  autodeploy on main; migrations run at backend boot), the CLI publish
  (version bumped 0.1.366 → 0.1.367 in root `pyproject.toml`), and the
  **first-ever `stash-sdk` publish** (pending trusted publisher is armed
  on PyPI: project `stash-sdk`, repo Fergana-Labs/stash, workflow
  publish.yml, environment pypi).
- **Session folders are alive as a quarantined legacy lane.** Migration
  0190 is a no-op (its docstring tells the story). The old read path
  shapes (`/me/transcripts/{id}`, `/{id}/events`, `/{id}/export.jsonl`,
  `/me/sessions/{id}`, `/{id}/title`, `/sessions/{id}`, materialize) are
  thin aliases registered after the static routes. The events model
  tolerates unknown fields but 422s the dead names
  (tenant_id/tenant_name/org_id/org_name). Nothing on the developer
  platform reads `session_folders`.

## Heavi facts (verified against prod Neon, project `little-scene-08473932`, read-only)

- Account: `stash@heaviai.com`, user id `24a1a14a-d412-4cdb-b799-461f17475108`.
- **No workspace** (their folders live on the plain account — this is why
  the original 0190 conversion would have skipped and then destroyed
  their grouping; that's the bug the no-op prevents).
- 24 keyed `session_folders`, 442 filed sessions, writes ongoing hourly.
- ~1.7k transcript reads/month via API key on the OLD path shapes (hence
  the aliases). Heavy `ask`/`scan`/`web` reads are server-side/lockstep.
- 29 other active accounts also file sessions into folders via installed
  clients; Henry has accepted degradation for them (they keep working at
  the API level anyway; they lose folder UI and new-client pinning).

## Merge-day runbook

1. Preconditions: CI green on head; a human watching for ~20 minutes.
2. Merge #1075 (Henry merges; never merge on his behalf).
3. Watch the deploy: Render MCP → `stash_backend` (slug `moltchat`)
   `list_deploys` / `list_logs`. Expect alembic `0188 -> 0189 ... -> 0197`
   at boot. A failed migration blocks the deploy and old code keeps
   serving — that is the designed failure mode, not an emergency.
4. Verify Heavi's pulse (read-only Neon): newest `sessions.started_at`
   and `user_api_keys.last_used_at` for their user id should keep
   advancing past the deploy timestamp. Watch Render logs for 404/422
   spikes on `/me/transcripts/` and `/me/session-folders/`.
5. Verify publishes: GitHub Actions "Publish to PyPI" run → `stashai`
   0.1.367 and `stash-sdk` 0.1.0 both live. If the sdk job fails on the
   publish step, fix on the PyPI side and re-run via workflow_dispatch.
6. Smoke prod (needs a real account key, e.g. Henry's): old transcript
   path shape 200s; `/developer` console loads; Prompts page shows the
   install prompt.

## Phase two: the Heavi cutover (next week, deliberate)

Goal: Heavi gets the Developer Platform entry in their scope dropdown,
pre-populated with their 24 orgs as end users — moved on purpose with
Mike, never shifted underneath them.

1. **Coordinate with Mike first** (Henry sends; draft for him). Heavi's
   backend change is two calls: drop `POST /me/session-folders/get-or-create`,
   and send `user_id` (their org key) + `user_name` on event uploads
   instead of `session_folder_id`. Reads move to the query-param shapes.
2. **Write the conversion migration** (next free number). For accounts
   owning keyed folders without a workspace: create a workspace whose
   `scope_user_id` IS the account (schema allows it; add a
   `workspace_members` row for the account itself or the console gate
   won't open), create External Wiki + User Notepads folders, set
   `external_wiki_folder_id`, convert each keyed folder → `end_users`
   row (external_id = external_key; move the folder under User
   Notepads as the notepad), re-point `sessions.session_folder_id` →
   `sessions.end_user_id`, seed the external curator (copy the seed SQL
   from 0193). The original conversion logic to crib from is in git
   history: `git show e408d262^:backend/migrations/versions/0190_drop_session_folders.py`.
3. **Deploy in step with Heavi's backend change.** Their writes fail
   loudly (not mis-filed) during any gap.
4. **Sunset release after cutover confirms**: drop the legacy read
   aliases (marked LEGACY in transcripts.py / sessions.py / skills.py),
   the session-folders router+service, `session_folder_id` fields and
   stamping, the permission lookup entry, and finally the column+table
   in a migration. Grep for "LEGACY" and "legacy lane" — every site is
   marked.

## Gotchas for whoever works this next

- **Worktree DBs**: this worktree's dev DB was hand-reconciled after the
  migration renumbering (session-titles fold applied manually, stamped
  0197, `session_folders` recreated from prod schema). Other worktrees
  on old numbering will fail alembic; fix by dropping/recreating their
  `*_test` DBs and reconciling dev DBs the same way.
- **Backgrounded pytest**: capture full output to a file; piping through
  `tail` loses the failure details (bitten twice this session).
- **VFS glob expansion** (`stashvfs/shell.py::_expand_globs`) never
  expands an argument that follows an option flag — quotes are gone by
  shlex time, so position is the only signal. Don't "fix" that back.
- The install/backfill prompts live in
  `frontend/src/components/developer/agentPrompts.ts`; the install
  prompt's first line is a key placeholder the user fills in by hand —
  that's deliberate, several fancier designs were rejected.
- `cat /memory/*` is a broken idiom (directories); docs teach
  `cat /memory/*.md` + per-category reads. Fix examples, not the VFS.
