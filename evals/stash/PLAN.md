# Stash Plugin A/B Eval — Plan

## Thesis

Installing the stash plugin + pre-seeding a workspace with prior-session findings makes Claude Code solve handoff tasks with fewer tokens, fewer rediscovery steps, and at least equal pass rate.

## Arms

- **Arm A (baseline)**: plain Claude Code. No plugin. `stash` binary removed from PATH. No `CLAUDE.md` reference to stash.
- **Arm B (stash)**: Claude Code + stash plugin installed in an isolated `CLAUDE_CONFIG_DIR`. Workspace pre-seeded with events extracted from Session A.

## Tasks

Each task is a real handoff from `~/.claude/projects/-Users-henrydowling-projects-octopus*/`:
Session A = the one that discovered/designed something.
Session B = the one whose user prompt we use as the eval prompt.

| Task | Session A | Session B | Base SHA |
|---|---|---|---|
| **T1** browser_auth — apply device-flow to `stash login` | b24ae7d9 (2026-04-16 01:44 UTC) | ac7cef7b (2026-04-16 03:28 UTC) | `8cf1bfd` (Session A's landed output) |
| T2 auth0_button | 480ca17d | e39dd811 | TBD |
| T3 scope_merge | 480ca17d | 07a7f011 | TBD |

Start with T1 only. T2/T3 are copy-the-scaffolding.

## Metrics

Deterministic checks run before the judge. Then per-trial:

- Pass/fail (rubric-graded, LLM judge on Opus 4.7, temp=0).
- Tokens (input/output/cache read/cache create) from SDK `Result`.
- Tool call count, by tool.
- Wall clock.
- **Stash-first signal** (Arm B): any `stash history search|query` call before the first `Grep`/`Read`/`Glob`?
- **Rediscovery overhead**: count of `Grep`/`Read` on paths in `session_a_touched_paths`.
- Time-to-first-edit.

## Milestones

- **M0** — spike (today): one Arm A trial end-to-end. Capture works, diff works, pytest works.
- **M1** — v0 end-to-end: both arms runnable for T1, N=1, hand-curated seed events.
- **M2** — automated extractor + N=5 per arm + LLM judge with majority vote (3 runs).
- **M3** — T2 + T3.
- **M4** — degraded-seed sensitivity study (optional).

## Risks

1. SDK plugin loading — does `claude-agent-sdk` honor user plugins from `CLAUDE_CONFIG_DIR`? Spike required.
2. PATH contamination — strip `stash` from Arm A PATH.
3. Workspace delete API — verify before M1 or workspaces pile up on stash.ac.
4. Agents ignoring stash — add "prior session history is available in this workspace" to Arm B prompt.
5. LLM judge reliability — run 3×, majority vote.
6. Seed leakage — events must be observations, not prescriptions. Hand-review T1.
7. Cost — ~$200-400 for the full eval at M3. Budget before running N=5.
