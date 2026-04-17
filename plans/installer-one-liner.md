# stash.ac/install — one-line bash installer

Replace the agent-prompt-paste install with `curl -fsSL https://stash.ac/install | bash`.
Most of the work is already done — `stash connect` ships the questionnaire we
want to keep (scope → managed-vs-self-host → browser auth → workspace pick).
Plan is: build a thin bash wrapper that installs the CLI and hands off to
`stash connect`, plus add one new step at the end of the questionnaire that
detects installed coding agents and installs the matching plugin.

## Shape

- `www/public/install.sh` — the installer script. Served at `https://stash.ac/install` via a Vercel rewrite or a Next.js route handler returning `text/x-shellscript`. Single file, < 100 lines bash. Detects package manager (pipx > uv > pip --user), installs `stashai`, runs `stash connect`. Accepts `--self-host=URL` flag to skip the managed/self-host prompt.
- `cli/main.py` — extend `connect()` with **Step 4: Coding-agent plugin install** after the workspace step. Detects Claude Code / Codex / Cursor / Gemini / opencode / openclaw on PATH or in well-known config dirs; for each found, prompts and runs the agent's native plugin command. Uses the existing `questionary.select` style.
- `www/app/page.tsx` — primary CTA becomes the one-liner (rendered as a copyable code block with a Copy button). The current agent-prompt-paste install moves to a secondary "Have your AI agent set this up" expander.
- `README.md`, `docs/quickstart` — lead with the one-liner. The agent-prompt path stays documented as an alternate.

## Installer script logic

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Parse args
ENDPOINT_FLAG=""  # honors --self-host=URL or --endpoint=URL
for arg in "$@"; do
  case "$arg" in
    --self-host=*|--endpoint=*) ENDPOINT_FLAG="${arg#*=}" ;;
  esac
done

# 2. Pick installer
if command -v pipx >/dev/null; then INSTALL="pipx install stashai --force"
elif command -v uv >/dev/null;   then INSTALL="uv tool install stashai --force"
elif command -v pip3 >/dev/null; then INSTALL="pip3 install --user --upgrade stashai"
else
  echo "Need pipx, uv, or pip3. Install one of:"
  echo "  brew install pipx        (macOS)"
  echo "  python3 -m pip install pipx"
  exit 1
fi

# 3. Install or upgrade
echo "→ Installing stashai via ${INSTALL%% *}…"
$INSTALL >/dev/null

# 4. Confirm on PATH
if ! command -v stash >/dev/null; then
  echo "stash installed but not on PATH. Add ~/.local/bin to PATH and re-run."
  exit 1
fi

# 5. Hand off to the questionnaire
if [ -n "$ENDPOINT_FLAG" ]; then
  exec stash connect --endpoint "$ENDPOINT_FLAG"  # skips the managed-vs-self prompt
else
  exec stash connect
fi
```

## New `connect()` Step 4: agent plugin install

After the workspace step (and before the welcome splash), detect installed
coding agents and offer to install the matching stash plugin. One-by-one so
the user can opt in/out per agent.

```python
# --- Step 4: Coding-agent plugins ---
detected = _detect_agents()  # returns [("Claude Code", "claude", install_cmd), ...]
if not detected:
    console.print("  [dim]No coding agent detected — install a plugin later "
                  "with `stash plugin install <agent>`.[/dim]")
else:
    console.print("\n  Detected coding agents on this machine:")
    for name, slug, _ in detected:
        console.print(f"    • {name}")
    if questionary.confirm(
        "Install the stash plugin for each?", default=True
    ).ask():
        for name, slug, install_cmd in detected:
            console.print(f"  → Installing stash plugin for {name}…")
            subprocess.run(install_cmd, check=True)
```

Detection heuristics (cheap, no shelling out for version checks):

| Agent       | Detect via                                       | Install command                                              |
|-------------|--------------------------------------------------|--------------------------------------------------------------|
| Claude Code | `command -v claude`                              | `claude plugin marketplace add Fergana-Labs/stash && claude plugin install stash@stash-plugins` |
| Codex CLI   | `command -v codex` or `~/.codex/`                | (per `plugins/codex-plugin/README.md`)                       |
| Cursor      | `~/Library/Application Support/Cursor/` (mac) or `~/.config/Cursor/` (linux) | (per `plugins/cursor-plugin/README.md`)                      |
| Gemini CLI  | `command -v gemini`                              | (per `plugins/gemini-plugin/README.md`)                      |
| opencode    | `command -v opencode`                            | (per `plugins/opencode-plugin/README.md`)                    |
| openclaw    | `command -v openclaw`                            | (per `plugins/openclaw-plugin/README.md`)                    |

Each plugin's existing README already documents its install command — we just
wrap them.

## Landing page changes

- Hero install block becomes a **bash one-liner** rendered like the other
  CLI sites (`fly.io`, `bun.sh`, `opencode.ai`):
  ```
  curl -fsSL https://stash.ac/install | bash
  ```
- One-line copy button. Below: "Self-hosting? Append `-s -- --self-host=https://your.host`."
- The current Claude-Code-prompt-paste block moves down to a secondary
  "Have your AI agent set this up" disclosure (some users will prefer it for
  their own reasons; keeping it costs nothing).

## Files to touch

| File                                          | Change                                                   |
|-----------------------------------------------|----------------------------------------------------------|
| `www/public/install.sh`                       | New — the installer script                               |
| `www/next.config.ts`                          | Rewrite `/install` → `/install.sh` with the right MIME   |
| `www/app/page.tsx`                            | Hero one-liner; demote agent-prompt block                |
| `cli/main.py`                                 | Add Step 4 to `connect()`; helper `_detect_agents()`     |
| `cli/main.py`                                 | (Optional) `stash plugin install <agent>` standalone cmd |
| `pyproject.toml`                              | Bump to 0.1.4                                            |
| `README.md`, `docs/quickstart/page.tsx`       | Lead with one-liner                                      |

## Explicitly NOT in scope

- Bundling stashai as a pre-built binary (Go/Rust style). Python+pipx is fine
  for now; binary distribution is a separate, much bigger lift.
- Auto-installing pipx/uv/pip if missing. The installer surfaces a clear "go
  install one of these" message and exits — better than silently bringing in
  Python tooling the user may not want.
- Fully unattended install (`--yes` / `--non-interactive`). The questionnaire
  is the point. We'll handle the agent-driven case via the existing prompt
  path, and self-hosters get `--self-host=URL` to skip one prompt.
- A `stash uninstall` script. Out of scope; users can `pipx uninstall stashai
  && rm -rf ~/.stash && claude plugin uninstall stash`.

## Risks

- **Hosted shell scripts can change without warning.** Mitigation: keep the
  script tiny and self-contained (no further `curl … | bash` chains), pin
  version strings, sign the published file or check a commit SHA in the URL
  for paranoid users.
- **PATH issues after install** (pipx writes to `~/.local/bin`, which isn't
  on PATH on a fresh macOS). The script detects this and surfaces an
  actionable message rather than silently failing.
- **Two install paths to keep in sync** — the bash one-liner and the agent
  prompt. The agent prompt currently does steps 1-5 inline; if we change
  the questionnaire, we have to update the prompt too. The fix is to make
  the prompt itself just `curl -fsSL https://stash.ac/install | bash` — at
  which point there's only one path.

## Rollout

1. **Phase 1 (CLI):** ship `connect()` Step 4 + version bump + PyPI publish.
   No landing-page change yet.
2. **Phase 2 (script):** ship `www/public/install.sh` + the rewrite. Test
   `curl … | bash` end-to-end on a fresh box.
3. **Phase 3 (landing):** swap the hero CTA to the one-liner; demote the
   agent-prompt block. Update README and docs.
4. **Phase 4 (cleanup):** simplify the agent-prompt path to just `curl … |
   bash` so there's a single source of truth for install logic.
