"""Shared curation prompt fed to each agent's headless CLI at session end.

Every plugin's `on_session_end.py` spawns its own agent binary (claude, codex,
cursor-agent, gemini, opencode) with this prompt. Each agent does the curation
using its own auth.
"""

SLEEP_PROMPT = """\
# Sleep Time Compute — Stash Wiki Curation

Curate workspace history into organized, categorized wiki pages. This is the
"sleep agent" workflow: read recent activity, analyze it, and write structured
knowledge into a notebook with categories, summaries, and [[wiki links]].

Use the `stash` CLI for everything — every subcommand supports `--json`.

## Steps

1. **Determine workspace.** The workspace ID comes from the `.stash/stash.json`
   manifest in the repo (or an ancestor). If no manifest exists, run
   `stash workspaces list --mine --json` and pick the appropriate workspace.

2. **List notebooks.** Run `stash notebooks list --ws <workspace_id> --json`.
   Look for an existing curation notebook (named "Wiki", "Knowledge Base", or
   similar). If none exists, create one:
   `stash notebooks create "Wiki" --ws <workspace_id> --json`.

3. **Read recent history events.**
   `stash history query --ws <workspace_id> --limit 200 --json`.
   Narrow by agent or event type with `--agent <name>` or `--type <event_type>`
   if the result set is noisy.

4. **Read existing wiki pages.** Get the current state of the notebook:
   `stash notebooks pages <notebook_id> --ws <workspace_id> --json`. Then
   read key pages (especially category index pages) with
   `stash notebooks read-page <notebook_id> <page_id> --ws <workspace_id> --json`
   to understand what already exists.

5. **Analyze and plan.** Compare the history events against existing pages.
   Determine what to:
   - **Create** — new topic pages for subjects not yet covered; new category
     index pages for emerging themes.
   - **Update** — add new information to pages that already cover the same topic.
   - **Merge** — combine duplicate or overlapping pages into one authoritative
     page. Keep the better title.
   - **Skip** — ignore events with no lasting value (routine tool calls,
     trivial status checks, ephemeral debugging).

6. **Execute.** Apply the plan with the CLI:
   - Create: `stash notebooks add-page <notebook_id> "Page Title" --ws <workspace_id> --content "markdown with [[wiki links]]"`
   - Update: `stash notebooks edit-page <notebook_id> <page_id> --ws <workspace_id> --content "updated markdown"`

7. **Report.** Summarize what was created, updated, merged, or skipped with a
   one-line description per page.

## Curation guidelines

- **Categorize everything.** Every page belongs to a category; category pages
  are index pages listing and linking all content in that topic area.
- **Use [[wiki links]] liberally.** Connect related pages. Every page should
  link to its category index and to related topics.
- **Merge duplicates aggressively.** If two pages cover the same topic, merge.
- **Delete noise.** Skip routine tool calls, trivial status checks, ephemeral
  debugging sessions.
- **Keep content concise.** Write summaries, not transcripts. A wiki page
  should be scannable in 30 seconds.
- **Preserve attribution** when relevant ("Discovered during session X",
  "Reported by agent Y").
- **Date-stamp updates.** When updating a page, add a date marker so readers
  know when information was added.

Begin now.
"""
