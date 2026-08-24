# Agent routes

The cloud agent (sprites) is driven through a small number of routes. Each
route decides how much the agent's toolset is trusted:

| Route | Trigger | Trust | Toolset |
|-------|---------|-------|---------|
| Web chat | Logged-in owner in the app | Trusted | Full |
| Channel (Slack/Telegram) | Unauthenticated message from an untrusted surface | **Untrusted** | Channel denylist applied |
| Scheduled | Cron-style agent runs (curator included) | Trusted prompt | Full |

## Harnesses

Each harness is one coding-agent CLI running headless on the user's sprite
(Claude Code, Codex, opencode, pi against the user's local model endpoint).
Command building and transcript mapping live in `backend/services/harness.py`;
session orchestration (locks, history, reseed) in
`backend/services/sprite_agent_service.py`.

### Per-channel tool restrictions

Channel messages are untrusted input, so a channel turn runs with the
harness's **channel denylist** — one per-harness constant
(`Harness.channel_disallowed` in `backend/services/harness.py`, in that
harness's own tool-name spelling). That constant is the single source of
truth: `run_chat` passes it to argv building on channel turns only, and
scheduled/web turns keep their full toolset.

- **Claude Code** — `Write`, `Edit`, `NotebookEdit`, `Bash(rm:*)`
  (`--disallowedTools`), byte-identical to the removed `SLACK_DISALLOWED_TOOLS` constant.
- **pi** — read-only: `write`, `edit`, `bash` via the headless flag
  `--exclude-tools write,edit,bash`. pi has no command-granularity bash rule,
  so bash is excluded wholesale — read-only is the only way to close the
  mutation vector. The flag is verified on the pinned pi `0.84.2`: it trims
  the model's tools array (baseline `read,bash,edit,write` → `read`) and an
  excluded call rejected at execution comes back `isError` with no side
  effect. The flag rides the reseed path, which rebuilds the argv.
- **Codex** — read-only sandbox: channel turns replace the production argv
  tail `--dangerously-bypass-approvals-and-sandbox` with `--sandbox
  read-only` (argv building in `harness.py` applies the swap when the
  denylist is provided; scheduled/web turns keep the bypass flag, byte-
  identical). `exec_command` stays model-visible, so the denylist names it —
  but the sandbox blocks its filesystem writes at execution time (OS-level
  read-only filesystem): verified on codex `0.146.1`, forced `touch` and
  shell-redirect file creation both fail (`Read-only file system`) with no
  file, `cat /etc/hostname` still succeeds, and a forced in-band
  `sandbox_permissions: "require_escalated"` override is rejected by the
  tool router before execution (`approval policy is Never; reject command`).
  Residuals: shell execution still works on channel turns — only filesystem
  WRITES are blocked (same class as Claude's `Bash(rm:*)` allowance); the
  sprite base-image codex version is not pinned in this repo, so a live-
  sprite re-check of the same probes is required if that version drifts.
- **opencode** — permission-deny config: channel turns ride a per-turn env
  var (merged over the provider env in `_turn_events`, never set for
  scheduled/web turns): `OPENCODE_CONFIG_CONTENT` carrying a deny for
  exactly the three mutation tools (`bash`, `edit`, `write`, each
  `"deny"`). The denylist names them; the env's deny map is pinned to it by
  test. The argv is
  untouched on every turn. Verified on the pinned opencode `1.17.18`:
  the deny strips the three tools from the model-visible array (10 → 7,
  `read`/`glob`/`grep`/`webfetch` stay) AND refuses forced calls at
  execution (`Model tried to call unavailable tool …`), for every mutation
  vector — including under the legacy `--dangerously-skip-permissions`
  auto-approve flag, which explicit denies survive. The wildcard
  `{"*": "deny"}` was proven over-broad (it removed ALL ten tools, leaving
  the turn useless) and was rejected. Residuals: the `task` sub-agent tool
  is not denied (parity with pi's deny set; sub-agents run under the same
  instance-level permission config), and `webfetch` is a read vector, not a
  box-mutation vector.
