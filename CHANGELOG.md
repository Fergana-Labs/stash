# Changelog

This file tracks user-visible changes. v0 is the open-source baseline —
everything before it is captured in git history (`git log`), not here.

## Unreleased

- Start trace messages collapsed, including assistant messages, with previews and
  consistent neutral row labels. Call assistant messages “Assistant” throughout.
  Replace task score cards with compact, unboxed headers containing inline values
  and the step range, without explanatory captions.
  Use a compact outline icon to return to the sections overview.

- Replace the separate Show less row with a subtle collapse icon in the message's
  left gutter, with a tooltip explaining that it collapses the text to a preview.

- Keep same-named files in connected Google Drive folders separately indexed,
  preserving each file's contents through renames and repeat syncs. Report
  duplicate skill names with the documents to choose from instead of silently
  loading one of them.

- Align the sticky Show less control with the left edge of message content.

- Add trace comments through a context menu, including selections spanning multiple
  messages. Left/Right now move between steps from the trace view; Enter opens
  sections and Esc goes back. Messages and tool calls start fully expanded.
  Show only the thin position line on the minimap, without a focus rectangle.

- Default trace credit charts to ±1 and omit the inactive Sections heading at
  the overview level. Fit scaling and navigation within sections remain available.

- Add Fit / ±1 trace-credit scaling and use baseline ticks for unscored steps.
  Separate task score summaries from message rows, with the task's step range,
  final answer, total work, and capped score. Show every suggested training base
  model in the picker and clarify that evaluation uses separate source traces.

- Plot step credit around a centered zero line: positive bars rise, negative bars
  fall, and zero has no filled height. Add an explanatory rescore tooltip.

- Keep the trace minimap marker on the selected step after a jump by matching
  scroll tracking to the space reserved for the sticky breadcrumb. Preserve
  clicked selections when a jump reaches the bottom, until the viewer scrolls
  or navigates elsewhere.

- Align trace step numbers with their message headings and move the theme toggle
  to the bottom-left sidebar.
- Leave sections containing only supplied context ungraded instead of assigning
  success scores to system instructions, requests, or tool observations.

- Simplify trace navigation and remove the label summary, Labels/Scores toggles,
  scoring explainer, and redundant navigation hints. Keep long-message collapse
  controls visible while scrolling, use warm Stash colors in dark mode, and show
  ungraded messages as minimap dots with single-line previews below the chart.

- Recover locally rejected long-trace scoring jobs after upgrading the worker.
  Hover statuses distinguish failed, queued, and running scoring jobs.

- Keep all recorded messages chronological, with compact inline expansion,
  left-gutter step numbers, syntax-highlighted code, and collapsible input and
  output rows. Remove the separate message reader and add a persistent theme toggle.
- Keep section cards one click away while the step view can scroll through the
  entire trace. Preserve the global minimaps, including navigation before scores
  arrive, and show action credit inline.
- Replace noisy scoring errors with a compact rescore control. Process long
  recordings in bounded, overlapping context windows instead of rejecting them;
  automatically resume traces rejected by the previous size limits.
- Show creation and training status for reward models trained on the current trace.
- Open single-task traces directly on their subtasks or recorded steps. Show
  readable section titles immediately while generated summaries load.
- Add local trace snapshot imports that retain saved grades and a lightweight
  worker for remote API scoring of new local imports.

- Organize traces by requests, progress subtasks, and distinct activities without
  capping section counts or splitting work into equal chunks. Generate concise
  activity titles and summaries. Let longer lists scroll, and use up/down
  arrows to select, right to open, and left to return to the parent section.
- Keep the left trace minimap at the whole-trace scale inside subsections,
  highlighting the containing task. Scrub between global tasks without changing
  the map’s scale; arrow navigation resumes afterward.
- Show cached section success scores with local objectives and an explanation.
  Judge each partition against the requests active within it, including unrelated
  tasks in the same conversation; insufficient evidence stays unscored.

- Browse long traces from request summaries into smaller sections and individual
  steps, with hover previews and direct minimap/comment navigation.
- Count adjacent tool calls and outputs as one displayed step. Render question
  replies and tool values readably while preserving source links and comment selections.
- Align plain action-credit numbers, remove full-row score colors and duplicate
  Details buttons, make user messages collapsible, and start comments closed.
- Load compact saved action and outcome scores together with the trace, avoiding
  a second download of evaluator prompts and responses before bars appear.

- Display embedded screenshots inline in traces, with click-to-enlarge previews.
  Re-uploading a native transcript restores its images without changing existing
  steps, comments, or scores.
- Give ungraded trace events no bar height, removing the alternating stripes
  while preserving their hover, click, and scrub positions.

- Replace blank trace scores with visible loading, queued, recalculating,
  waiting, insufficient-evidence, or failure statuses.

- Start the comments panel closed on traces with no comments, while preserving
  manual open/close choices during updates.
- Make the first trace navigation tick jump to the very top, including system messages.

- Move trace sharing into the three-dot actions menu.

- Remove the trace's Expand all control; individual tool details still open on demand.

- Scrub through traces and conversations by dragging along the left navigation
  rail, with immediate scrolling and a live preview of each destination.
- Keep trace controls in two compact rows: back, title, score, and actions above
  the step map. Remove the All / Conversation / Tools toggle and keep all steps
  visible. Move execution timelines into the scrolling content.

- Remove the action-credit legend and visible annotation-progress row to give
  the trace more vertical space, and place the imported timestamp beside the
  title. Scores and grading statuses remain available on hover and focus, with
  a progress summary for screen readers.

- Use continuous expected action credit from −1 to +1, calculated from saved
  classifier probabilities, across trace bars, credit summaries, and new training
  comparisons. Preserve insufficient-evidence abstentions and original verdicts.
- Remove the trace-map instruction line and show action scores or grading status
  immediately on hover or keyboard focus, replacing delayed native tooltips.

- Explain trace-bar heights with a harmful/neutral/helpful legend and show
  annotation counts, pending scores, insufficient evidence, and failed updates.
  Retry invalid automatic-classifier responses up to three times per batch,
  retaining completed batches and recovering previously stranded annotations.

- Keep previous action-credit bars visible while a growing trace is evaluated
  again. Earlier annotations are clearly labeled and replaced as current scores
  arrive; unscored new steps no longer make the entire chart appear to collapse.

- Simplify the latest reward-model workspace to Traces, Reward models, and
  Monitoring, with current skills, changes, and feedback under Monitoring.
  Search trace content, review numeric success and action-credit summaries,
  and share traces with teammate name suggestions.
- Keep the trace minimap visible, color bars by action type, size them by credit,
  and jump to the exact selected step. Remove evaluation-history panels and
  align conversation rows consistently.
- Train personal reward models from saved automatic action and outcome
  annotations. Keep training and evaluation tasks separate, exclude stale or
  disputed labels, and monitor saved model scores on recorded runs.

- Reward-model links on the marketing site open the app, and the trace-list
  alias `/reward-models/traces` redirects to `/reward-models` instead of a 404.

- Automatically extracted corrections retain the conversation and tool results
  through the user's feedback when drafting agent instructions. Unreviewed target
  guesses can be corrected or left unresolved. Older untouched drafts are archived
  and regenerated once; human reviews and released instructions are preserved.

- Automatic Jev evaluation recovers traces skipped during rolling deployments
  and retries stale database query plans. Migration backfill preserves active
  workers. Corrections without a recorded repository can still be interpreted
  and reviewed; only instruction creation remains unavailable. Recovery respects
  accounts using an older product checkpoint or with workbench access disabled.

- Skill generation automatically retries invalid model-generated names and
  descriptions, so an overlong description no longer immediately fails the job.

- Open traces, session transcripts, and chats have a slim conversation rail:
  hover a tick to preview a turn, click to jump, or navigate with the keyboard.
  Reading an earlier chat turn now holds your place while a response streams.
  Trace turn previews use assistant responses rather than thinking events, and
  transcript navigation also works in the Developer Platform console.

- Accounts can be assigned the October 5 Floodgate product checkpoint, retaining
  its Traces, Reward models, and Skills experience in the main app.

- Automatic Jev evaluations no longer stop at a daily call limit. Traces paused
  by the previous cap resume automatically and reuse their saved results.

- Agent Workbench automatically uses Jev to judge trace success and estimate each
  action’s credit from recorded results. No grader setup is required. Inspect
  saved evidence, confidence, previous trace versions, and evaluation errors
  separately; corrections can propose repository-scoped agent instructions.

- New signups see only the Developer Platform, with internal navigation,
  onboarding, and settings hidden by a per-user flag. Existing accounts retain
  both interfaces.
- Developer curation enforces sharing in backend tools: opted-out inputs stay
  in separate private runs that cannot write to the shared wiki. Developer
  curators use the backend Anthropic model without workspace credentials or
  shell access. Opting out archives the previous shared corpus privately and
  rebuilds from permitted inputs; existing opt-outs are migrated on deployment.
- External curator audit details now stay in run transcripts. Existing shared
  `Log` and `changelog` pages move to a private workspace archive, with public
  and explicit page shares removed.
- CLI onboarding redesigned (#940). `stash signin` walks a first-run wizard
  that can be re-run anytime with the new `stash setup` — no answer is final.
  Session recording is framed as private-by-default and on by default
  (`stash stop` pauses). The agent picker uses `[x]` checkboxes where enter
  toggles and a `Done` row saves. `stash connect` works in any folder — a git
  repo is no longer required. History import runs in the background via the
  new `stash import-history` (parallel uploads; `--status` attaches a live
  progress bar). Re-uploading a transcript for a deleted session now reports
  a clean skip instead of a 404 error, and no longer pollutes plugin upload
  health.
- `stash memory` is now a command group (#941): `stash memory write "<Path>"`
  creates or updates a Memory wiki page (stdin for long bodies) and
  `stash memory ls` prints the wiki tree — the direct write surface for
  agents that maintain the wiki themselves. Bare `stash memory` and
  `--recompute` are unchanged.
- The nightly cloud Memory curator has an off switch (#942):
  `stash memory --curator off|on`, also surfaced in the web curator panel.
  On-demand recomputes keep working while it's off.
- Scheduled agent run history now reports each run's status, error, duration,
  event count, and tool count while preserving the chronological transcript
  feed used by the agent workspace.
- Scheduled agent runs no longer crash in local dev mode: the MCP registry's
  `.mcp.json` is now written to the local simulated workdir instead of the
  literal `/home/sprite/work` path, which is unwritable on dev machines.
- Gong call documents now link back to the original call in Gong.
- `stash vfs stat` once again shows the source-sharing command for connected
  source roots, including roots that do not have an app URL.
- OAuth reconnects now require a stable provider account identity. Slack,
  Asana, Jira, Linear, Notion, and Gong connections refuse to store new
  credentials when identity lookup fails, preventing retained source data
  from silently continuing under a different provider account.
- Frontend server-side backend requests now require `BACKEND_INTERNAL_URL`
  or `NEXT_PUBLIC_API_URL` instead of guessing an environment, so missing
  managed deploy config fails during build rather than crashing public
  Stash pages at runtime.
- Added a committed `docker-compose.local.yml` override for laptop
  self-hosting dry runs. It exposes backend, frontend, and collab on
  localhost ports and disables Caddy.
- Self-hosting now uses a prebuilt `ghcr.io/fergana-labs/stash-frontend`
  image alongside the backend and collab images, so
  `docker-compose.prod.yml` no longer builds application containers on the
  target machine.
- Backend now routes markdown and HTML uploads to the pages table on the
  one upload endpoint, so every surface (frontend drag-drop, CLI `stash
  files upload`, MCP `stash_upload_file`) gets the same behavior. The
  response is a discriminated `{kind, ...}` payload — `kind: "page"` for
  md/html, `kind: "file"` for everything else.
- MCP server gained ten tools to reach parity with the CLI on agent-
  useful surfaces: discover (`stash_search_public_stashes`,
  `stash_read_public_stash`), page search (`stash_search_pages`),
  session ops (`stash_session_transcript`, `stash_delete_session`),
  invite management (`stash_create_invite`, `stash_revoke_invite`),
  stash access control (`stash_set_stash_access`), and table tooling
  (`stash_update_table`, `stash_export_table`).
- Renamed the three unprefixed MCP tools to share the `stash_` prefix
  with the rest of the surface: `stash_list_trash`, `stash_restore`,
  `stash_purge`.
- Added `BACKEND_INTERNAL_URL` env var so docker / self-host deployments
  route the Next.js server-side fetches at the in-network backend
  hostname instead of looping through the public URL. Public Stash pages
  no longer 500 on a fresh self-host boot.
- Added `INTEGRATIONS_ENCRYPTION_KEY`, `ANTHROPIC_API_KEY`,
  `ANTHROPIC_MODEL`, and `ANTHROPIC_FAST_MODEL` to `.env.example` —
  every variable `backend/config.py` actually reads is now in the
  reference file.
- Refreshed user-facing docs (`README`, `ARCHITECTURE`, `USE_CASES`,
  `DESIGN`, the `frontend/docs/*` pages) to match shipped product
  surface: real concept names, real CLI commands, real container set
  for self-hosting.
- Bumped the Claude Code plugin to 0.1.84 so the cached
  SessionStart context refreshes — older versions injected
  `stash history *` / `stash notebooks list` references to commands
  that no longer exist.
- Added `stash vfs`, an app-level virtual filesystem shell for browsing
  Stash with bash-shaped commands and editing existing writable pages.
- Kept `stash mount` hidden as experimental spike code; the supported
  production path is `stash vfs`.

## v0

Initial open-source release.
