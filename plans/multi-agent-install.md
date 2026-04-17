# Multi-agent install (Cursor, Codex, opencode)

Kill the "paste this prompt into Claude Code" framing on the landing
page. Replace it with a plain shell block — the user pastes bash into
their terminal, the CLI wires up every agent it finds on `$PATH`. Today
the prompt hardcodes `claude plugin marketplace add …`, Cursor/Codex/
opencode have no equivalent command, and their plugin files don't ship
on pypi — so a fresh `pipx install stashai` can't install them.

## Shape

- **`stashai/plugin/assets/`** — ship the three plugin templates as
  package data so they're on disk after `pipx install stashai`:
  - `cursor/hooks.json.tpl` (copy of `plugins/cursor-plugin/hooks.json`)
  - `codex/hooks.json.tpl` + `codex/config.toml.snippet`
  - `opencode/plugin.ts` + `opencode/package.json`
  - `__init__.py` exposes `assets_dir(agent) -> Path` via
    `importlib.resources`.
  - `plugins/<agent>-plugin/` stays the source of truth; a `conftest`-style
    assertion in `plugins/tests/` diffs the two on every CI run so they
    can't drift.

- **`stash install`** — new CLI command in `cli/main.py`. Default
  behavior: **install for every supported agent on `$PATH`**. A machine
  with `claude` + `cursor-agent` + `opencode` gets all three wired up
  from one paste; the agent the user later runs already streams. Each
  per-agent branch is idempotent — re-running is a no-op.

  Detection rule: `shutil.which("claude")`, `"cursor-agent"`,
  `"codex"`, `"opencode"`. Absent binaries skipped silently. Closing
  summary line: `installed: claude, cursor, opencode  skipped: codex (not on PATH)`.

  Per-agent branches:
  - `claude`  → shells out to `claude plugin marketplace add Fergana-Labs/stash`
    then `claude plugin install stash@stash-plugins`. Parity with the
    current prompt.
  - `cursor`  → `PLUGIN_ROOT=~/.stash/plugins/cursor` (mkdir, copy
    `scripts/` from the shipped assets), `envsubst` the hooks template
    into `~/.cursor/hooks.json`.
  - `codex`   → same pattern into `~/.codex/hooks.json`, then append the
    `config.toml` snippet to `~/.codex/config.toml` *if the marker line
    `# stash-plugin` isn't already present* (idempotent merge).
  - `opencode` → copy `plugin.ts` to `~/.stash/plugins/opencode/`, then
    JSON-merge `{"plugin":["…/plugin.ts"]}` into
    `~/.config/opencode/opencode.json` (create file if missing; preserve
    other keys).

  Flags:
  - `stash install <agent>` — install only that one (rare case: user
    doesn't want streaming from one of the installed agents).
  - `--skip <agent>[,<agent>]` — install everything except these.
  - `--force` — overwrite existing hook files without prompting. Without
    `--force`, an existing `~/.cursor/hooks.json` prompts
    `[y/N/diff]` before overwrite.

- **Blocking `stash signin`** — today `signin` opens the browser and
  exits, leaving the user to copy the token into a second `stash auth`
  command. Two paths, picked automatically by environment:

  **Local (default, `gh`-style localhost callback):**
  - CLI starts `http.server` on `127.0.0.1:<random-port>` with one
    route: `GET /cb?token=<key>`.
  - CLI calls `webbrowser.open("https://stash.ac/connect-token?cb=http://127.0.0.1:<port>/cb")`.
  - `www` `/connect-token` page mints the key, then JS-redirects to
    the `cb` URL with the key on the querystring.
  - Local handler captures the token, writes `~/.stash/config.json`,
    runs the same auto-workspace logic `stash auth` has today, returns
    a "✓ signed in — you can close this tab" HTML response, shuts the
    server down.
  - No backend endpoints, no polling — everything stays in the CLI.

  **SSH fallback (device-code style):**
  - Trigger: any of `$SSH_CONNECTION`, `$SSH_CLIENT`, `$SSH_TTY` set,
    OR `webbrowser.open` returns `False`. `--no-browser` flag forces
    this path.
  - CLI generates `session_id` (uuid4), prints:

        Open this URL on your local machine:
          https://stash.ac/c/<session_id>

    Modern terminals make it clickable; worst case it's one URL copy
    (not a token paste).
  - `www` `/c/<session_id>` page mints the key, `POST`s it to
    `POST /auth/cli-session/<session_id>` on the backend with a 5-min
    TTL row (new `cli_sessions` table; four cols: id, token,
    base_url, expires_at).
  - CLI polls `GET /auth/cli-session/<session_id>` every 1s for up to
    120s. On hit: write config, auto-workspace, exit 0. Timeout → hint
    at `stash auth --api-key` and exit 1.

  **Shared endings:** timeout / failure always leaves the user able to
  run `stash auth <url> --api-key <key>` by hand; that path stays
  supported for self-host and CI.

- **Landing page** (`www/app/page.tsx`) — replace the natural-language
  prompt block with a single shell line:

      pipx install stashai && stash install && stash signin

  Rip out the "paste into Claude Code" / `PromptBody` / backtick-parsing
  component and the "claude code" / "prompt" chrome labels. Replace with
  a `<pre>` code block styled like other code blocks. Caption:
  "Run in any shell. Installs plugins for every coding agent on your
  PATH." No `stash.ac/connect-token` callout — `stash signin` handles
  everything in-band.

  `uv tool install` fallback is a secondary bullet below the main line
  for users without pipx — don't stuff it into the headline one-liner.

- **Verification on this machine** — after shipping:
  - `stash install cursor` → open a new Cursor chat, send a message,
    `stash history query --limit 5` shows a `user_message` event.
  - Same for `codex` (via `codex` one-shot) and `opencode` (via
    `opencode run`).
  - Re-running `stash install <agent>` is a no-op (idempotent).

## Explicitly NOT in scope

- **Gemini CLI + Continue + Windsurf.** Gemini plugin exists in-repo but
  Gemini isn't installed on this machine; add once Henry actually runs
  it. Continue is a VSCode extension (different surface). Windsurf has
  no plugin yet.
- **Uninstall.** `stash install` only writes. Removing hooks is a manual
  `rm ~/.cursor/hooks.json` for now — add `stash uninstall` when a user
  asks.
- **Version pinning of plugin assets.** Templates ship with the stashai
  version the user `pipx`'d; `pipx upgrade stashai` gets them the new
  ones. No separate plugin-version channel.
- **Merging non-stash entries in `~/.codex/config.toml`.** We only
  append once; if a user hand-edits between installs we don't reconcile.
  Marker-line check prevents double-append, which is the only real
  failure mode.
- **Making `plugins/<agent>-plugin/` READMEs the install path.** They
  document the manual approach for contributors; the user-facing path
  is `stash install <agent>`.

## The one-liner

    pipx install stashai && stash install && stash signin

One paste → CLI installed, every detected agent wired up, user
authenticated with default workspace set. No second command, no token
copy-paste.
