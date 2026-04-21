---
description: Curate workspace history into the Stash wiki (sleep-time compute, on demand)
---

<!-- Body kept in sync with SLEEP_PROMPT in stashai/plugin/sleep_prompt.py. -->

# Sleep Time Compute — Stash Wiki Curation

Curate workspace history into an organized, categorized wiki. Read recent
activity, analyze it against the existing wiki, and write structured
knowledge as markdown pages with categories, [[wiki links]], and confidence
tags.

Use the `stash` CLI for everything — every subcommand supports `--json`.

## Operating principles

- **Bootstrap vs. maintain — know which mode you're in.** If the wiki is
  empty (no notebook, or notebook has no pages), you are bootstrapping
  from scratch: generate a category skeleton and seed pages from the
  history in one pass. If the wiki already has pages, you are
  maintaining: fold new info into the existing structure.
- **Maintain, don't regenerate.** Once the wiki exists, your job is to
  fold in new information, not rewrite what's there.
- **Scope by diff, not by corpus.** In maintenance mode, only touch pages
  whose topic appears in *this* batch of events. Leave untouched pages
  alone.
- **Category-first, pages-second.** Every page belongs to a category. A
  concept gets its own page only when it appears in >=2 distinct events
  (across sessions or within one). One-shot mentions stay as bullets on
  the category index.
- **Tag confidence.** Mark facts inline as `(extracted)` when the event
  states them directly, `(inferred)` when derived, `(ambiguous)` when
  uncertain. Never create a new page from ambiguous-only material.
- **Prefer updating to creating.** Before writing a new page, search
  existing pages for semantic overlap. If an existing page covers the
  same topic, update it instead.
- **Resolve contradictions explicitly.** When new events contradict an
  existing page, do not silently overwrite. Add a dated `## Updates`
  entry noting the old claim, the new claim, and which supersedes — with
  a one-line reason.

## Steps

1. **Determine workspace.** Workspace ID comes from the `.stash/stash.json`
   manifest in the repo (or an ancestor). If no manifest exists, run
   `stash workspaces list --mine --json` and pick the matching workspace.

2. **Locate or create the curation notebook.**
   `stash notebooks list --ws <workspace_id> --json`. Look for a notebook
   named "Wiki", "Knowledge Base", or similar. If none exists:
   `stash notebooks create "Wiki" --ws <workspace_id> --json`.

3. **Read recent history events.**
   `stash history query --ws <workspace_id> --limit 200 --json`.
   Narrow by agent or event type with `--agent <name>` / `--type <event_type>`
   when the result set is noisy.

4. **Read existing wiki state.**
   `stash notebooks pages <notebook_id> --ws <workspace_id> --json` to
   list all pages. Read every category index page and any page whose
   title plausibly overlaps with topics in step 3, via
   `stash notebooks read-page <notebook_id> <page_id> --ws <workspace_id> --json`.

5. **Branch: bootstrap or maintain?**

   **If the wiki is empty** (new notebook, or listed pages is empty):

   a. **Cluster the history.** Group the events from step 3 into 3-7
      coherent themes (e.g. "Auth refactor", "Ingestion pipeline",
      "Plugin install flow"). Themes come from repeated topics, not
      every one-shot mention.

   b. **Create category index pages first**, one per theme. Each index
      opens with a one-sentence scope, then a bulleted list of its
      child pages (initially empty, filled as you create them below).

   c. **Create seed pages** for concepts that appear in >=2 events
      within a theme. One-shot mentions get a bullet on the category
      index instead of their own page.

   d. **Cross-link as you go.** Every seed page links up to its category
      index with `[[Category: X]]` and sideways to related seed pages.
      Update each category index's child list as you add pages.

   e. **Skip step 7's orphan/stub checks on the very first bootstrap** —
      everything is new, so these checks would flag everything. Still
      run the broken-link check.

   **If the wiki already has pages** (maintenance mode), for each
   candidate topic from step 3, decide:

   - **Create** — topic is new, appears in >=2 events, not covered
     elsewhere. Assign it to an existing category index (or create a new
     category index if the topic is genuinely new).
   - **Update** — existing page covers this; merge in new info. If new
     events contradict the page, add a dated `## Updates` section rather
     than overwriting.
   - **Merge** — two existing pages cover the same topic. Pick the
     better title, consolidate content, rewrite backlinks from the loser
     to the winner, leave a one-line deprecation redirect on the loser
     ("Merged into [[Winner]] on <date>").
   - **Skip** — one-shot mention, routine tool call, ephemeral
     debugging, trivial status check. These never become pages.

6. **Execute.** Apply the plan:

   - Create: `stash notebooks add-page <notebook_id> "Page Title" --ws <workspace_id> --content "<markdown>"`
   - Update: `stash notebooks edit-page <notebook_id> <page_id> --ws <workspace_id> --content "<markdown>"`

   Every page should:

   - Open with a one-sentence summary.
   - Link up to its category index with `[[Category: X]]`.
   - Link sideways to related pages with `[[Other Page]]`.
   - Tag facts with `(extracted)` / `(inferred)` / `(ambiguous)`.
   - Date any content added this run with `<!-- added YYYY-MM-DD -->`.

7. **Audit.** Before finishing, scan for:

   - **Orphans** — pages with no incoming backlinks. Either link them
     from the right category index or merge if redundant.
   - **Stubs** — pages under ~3 sentences. Either expand from the
     history or merge into a broader page.
   - **Category gaps** — category index pages that don't list every page
     in that category. Fix the listing.
   - **Broken [[wiki links]]** — links pointing at non-existent pages.
     Either create the target or fix the link.

8. **Report.** One-line summary per action taken: created / updated /
   merged / skipped, with page titles.

## Hard rules

- Summaries, not transcripts. A page is scannable in 30 seconds.
- Merge aggressively. Two pages on one topic is always wrong.
- Never delete. Deprecate by rewriting into a redirect stub.
- Attribution when relevant: "Discovered during session X", "Reported by
  agent Y".

Begin now.
