# Repo-level Stash enablement

Goal: make Stash enablement a property of the *repo*, not each contributor's machine.
When someone clones a Stash-enabled repo and runs `stash connect` (or already has
the CLI), they're auto-joined to the right workspace and their agent starts
pushing to the team's shared memory — with no per-user setup.

Modeled on the way GStack attaches itself to a project via a committed marker
file.

## The two-file model

We already have `.stash/config.json` as a project-scoped config file. Today it's
a *local* override that's not meant to be committed. For repo-level enablement
we split this into two files living side by side in `.stash/`:

| File | Committed? | Purpose |
|---|---|---|
| `.stash/stash.json` | **yes** | Team manifest. Points every contributor at the same workspace. |
| `.stash/config.json` | **no** (gitignored) | Per-user local state — api_key override, per-repo opt-out flag. |

### `.stash/stash.json` (committed)

```json
{
  "version": 1,
  "workspace_id": "7b3a4f2e-1c9d-4a6b-9e2f-8c1d5b3a4f2e",
  "workspace_name": "Octopus Core",
  "invite_code": "oct-abc123",
  "base_url": "https://moltchat.onrender.com",
  "streaming_default": true
}
```

Contributor-facing fields only. No secrets — the invite code is designed to be
shareable.

### Why `invite_code` and not a magic-link token?

The CLI already has two invite mechanisms (see `cli/client.py`):

- **Workspace `invite_code`** — permanent, reusable, no TTL. Redeemed via
  `join_workspace(invite_code)` → `/api/v1/workspaces/join/{invite_code}`.
- **Magic-link tokens** — single-use (default `max_uses=1`), TTL'd (default
  `ttl_days=7`), revocable via `revoke_invite_token`. Redeemed via
  `redeem_invite_authed` / `redeem_invite_unauthenticated`.

We commit the workspace `invite_code` because it survives for the life of the
repo and works for every new contributor without maintainer involvement.
Magic-link tokens expire and max-uses out — they're the wrong primitive for a
committed manifest. The tradeoff is no revocation: rotating requires backend
support (workspace invite codes don't currently have a rotate endpoint).
Document this gap and treat `require_approval` (deferred to v2) as the real
access-control lever.

### `.stash/config.json` (gitignored)

Unchanged from today — per-user local overrides (`default_workspace`,
`output_format`, etc.). `stash init` auto-appends this path to `.gitignore`.

## New command: `stash init`

Run once by a maintainer to enable the repo.

```
$ stash init
Stash init — enable shared agent memory for this repo

  Workspace:   Octopus Core  (7b3a4f2e…)  ← your default
  Invite code: oct-abc123                  ← anyone who joins uses this

  Writing .stash/stash.json                  ✓
  Adding .stash/config.json to .gitignore    ✓

  Next: commit .stash/stash.json and push. Every teammate who runs
  `stash connect` in this repo will auto-join the workspace.
```

Steps the command performs:

1. Require an authenticated session. If not auth'd, run `stash connect` first.
2. Pick a workspace:
   - If `default_workspace` is set, offer that as the default.
   - Otherwise list owned workspaces + "Create new…".
3. Fetch the invite code for that workspace (reuse; do not rotate).
4. Write `.stash/stash.json` to the repo root (walk up from cwd to the git root;
   fall back to cwd if not in a git repo).
5. Ensure `.stash/config.json` is in `.gitignore` and `.stash/stash.json` is
   NOT. Three cases to handle:
   - No `.gitignore`: create one with `.stash/config.json`.
   - `.gitignore` has `.stash/` (wholesale): replace with `.stash/config.json`,
     or add `!.stash/stash.json` negation below it.
   - `.gitignore` has `.stash/config.json` already: skip.
6. Print the "commit this" instructions.

## Auto-join flow in `stash connect`

Inside `connect()` in `cli/main.py`, **manifest detection runs first** —
before the scope/endpoint prompts and before auth. Reading the manifest
decides which instance to authenticate against, so discovering it after auth
would waste the user's time if they're signed in to the wrong instance.

1. Walk up from cwd looking for `.stash/stash.json` (mirror the existing
   `find_project_config` helper).
2. If found, read it. The manifest is the source of truth for this repo:
   - Still show the "Where do you want to install stash?" prompt, but flip
     the default from `user` (machine-wide) to `project` (this repo only).
     Users who prefer machine-level install can still pick it — we're just
     steering new contributors toward the repo-scoped default that matches
     the manifest's intent. If they pick `user`, we still honor the
     manifest's `workspace_id` / `base_url`; the choice only affects where
     the resulting `default_workspace` config is written.
   - Bypass the "How do you want to use Stash?" prompt — `base_url` comes
     from the manifest.
   - Bypass the "which workspace?" prompt — `workspace_id` comes from the
     manifest.
3. If the user is already authenticated against a different `base_url`,
   prompt (see edge cases) and re-auth if they accept.
4. Check membership: `GET /api/v1/workspaces/<workspace_id>` — if 404/403, the
   user isn't in it yet.
5. Prompt:
   ```
   This repo is set up for the "Octopus Core" workspace on Stash.
   Join and start sharing agent transcripts with the team? [Y/n]
   ```
6. On yes: call `c.join_workspace(invite_code)`. On success, write
   `default_workspace=<workspace_id>` to the scope chosen in step 2 — project
   scope by default (`.stash/config.json`, so hooks in *this repo* push to the
   manifest workspace without disturbing the user's global default), or user
   scope (`~/.stash/config.json`) if the contributor explicitly opted into
   machine-wide install.
7. On no: write `stash_disabled_here=true` to `.stash/config.json` and skip.
   Hooks in this repo become inert.
8. If the user is already a member: skip the prompt, just write the project
   `default_workspace`.

When no manifest is found, `connect()` behaves exactly as today.

## Hook behavior change

`stashai/plugin/hooks.py` already short-circuits on empty `workspace_id` and
out-of-scope cwd (see `_short_circuit` at the top of that file). Once
`stash connect` has written `default_workspace` to `.stash/config.json`, hooks
in that repo will push to the manifest workspace automatically via
`load_config()` (project config overrides user config).

One small addition: if `stash_disabled_here=true` is set in the project
config, short-circuit the same way — treat it as "no workspace configured
for this repo." This keeps drive-by contributors who opted out from leaking
events. Consider whether this is redundant with simply clearing
`default_workspace` in the project config; if so, `stash disable` can just do
that instead of introducing a new flag.

## New command: `stash disable` / `stash enable`

Per-repo opt-out without touching the manifest.

```
$ stash disable
Stash streaming disabled for this repo (wrote .stash/config.json).
Run `stash enable` to turn it back on.
```

Flips `stash_disabled_here` in the project config.

## Edge cases

- **Manifest workspace deleted.** Membership check returns 404; show
  `[red]The workspace this repo points to no longer exists. Ask a maintainer
  to run stash init to update .stash/stash.json.[/red]` and skip.
- **Invite code expired/revoked.** Join call fails; same message as above.
- **No auth.** Run the existing browser auth flow first, then loop back to the
  manifest check.
- **Nested repos** (monorepo with sub-projects each having their own
  `.stash/stash.json`): the walk-up finds the innermost one, which is what
  we want.
- **User already authed on a different instance** (managed vs self-hosted).
  Manifest specifies `base_url`; we prompt:
  ```
  This repo uses https://moltchat.onrender.com but you're signed in to
  http://localhost:3456. Sign in to the repo's instance? [Y/n]
  ```
- **Drive-by contributor with no Stash installed.** Nothing happens. The
  manifest is inert until someone runs the CLI. This is intentional — we don't
  want to auto-install anything from a git clone.

## Security & trust

The manifest contains an invite code. Anyone who can clone the repo can join
the workspace. For public OSS repos this is too permissive, so:

- Print a warning on `stash init` if the current git remote looks public (GitHub
  public repo detection via `gh api` or a simple `git remote -v` heuristic).
- Manifest supports an optional `require_approval: true` flag. When set, joins
  go into a pending queue instead of auto-admitting. This needs backend support
  on the workspace invite endpoint (out of scope for v1 — document as future
  work).

For v1 we ship without `require_approval` and gate it on a warning in `stash
init` for public-looking remotes. Private repos / internal tools (our primary
audience per memory) don't need it.

## Rollout

1. **cli/config.py** — add `find_project_manifest()` that looks for
   `.stash/stash.json` (separate from the existing `find_project_config`).
   Add a `Manifest` TypedDict.
2. **cli/main.py** — add `stash init`, `stash enable`, `stash disable`.
3. **cli/main.py `connect()`** — insert manifest detection + auto-join between
   auth and the workspace prompt. Skip the prompt when a manifest is present.
4. **Splash screen** — when connect finishes via manifest, swap the "Invite
   your team" panel for a "Joined <workspace>" confirmation.
5. **stashai/plugin/hooks.py** — extend `_short_circuit` to also return True
   when `stash_disabled_here=true` is set in the project config (or just have
   `stash disable` clear `default_workspace` and skip this change entirely).
6. **README + CONTRIBUTING.md** — one short section: "This repo uses Stash. Run
   `stash connect` to join." Point at the install docs.

## Out of scope for v1

- Server-side `require_approval` workflow.
- Auto-install of the CLI on `git clone` (we won't ship a shell hook).
- Telemetry on how many contributors joined via a manifest vs. manual connect.
  Nice-to-have; wait for a second user asking.
