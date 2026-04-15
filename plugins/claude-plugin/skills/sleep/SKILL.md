---
name: sleep
description: "Sleep time compute -- curate workspace history into organized wiki pages with categories and [[backlinks]]. Run periodically or on-demand."
---

# Sleep Time Compute

Curate workspace history into organized, categorized wiki pages. This is the "sleep agent" workflow: read recent activity, analyze it, and write structured knowledge into a notebook with categories, summaries, and [[wiki links]].

## Steps

1. **Load config**: Run `octopus config --json` to get `default_workspace`. If not set, ask the user for the workspace_id.

2. **List notebooks**: Run `octopus notebooks list --ws <workspace_id> --json`. Look for an existing curation notebook (named "Wiki", "Knowledge Base", or similar). If none exists, ask the user which notebook to use or create one:
   ```bash
   octopus notebooks create "Wiki" --ws <workspace_id> --json
   ```

3. **Read recent history events**: Fetch the latest activity:
   ```bash
   octopus history query --ws <workspace_id> --limit 200 --json
   ```

4. **Read existing wiki pages**: Get the current state of the notebook:
   ```bash
   octopus notebooks pages <notebook_id> --ws <workspace_id> --json
   ```
   Then read key pages (especially category index pages) to understand what already exists:
   ```bash
   octopus notebooks read-page <notebook_id> <page_id> --ws <workspace_id> --json
   ```

5. **Analyze and plan**: Compare the history events against existing pages. Determine what to:
   - **Create**: New topic pages for subjects not yet covered, new category index pages for emerging themes
   - **Update**: Add new information to existing pages that cover the same topic
   - **Merge**: Combine duplicate or overlapping pages into one authoritative page
   - **Skip**: Ignore events with no lasting value (routine tool calls, trivial status checks)

6. **Execute changes**: Apply the plan using the CLI:
   - Create a new page:
     ```bash
     octopus notebooks add-page <notebook_id> "Page Title" --ws <workspace_id> --content "markdown content with [[wiki links]]"
     ```
   - Update an existing page:
     ```bash
     octopus notebooks edit-page <notebook_id> <page_id> --ws <workspace_id> --content "updated markdown content"
     ```

7. **Report**: Summarize what was created, updated, merged, or skipped. List the pages that changed with a one-line description of each change.

## Curation Guidelines

- **Categorize everything** -- every page belongs to a category. Category pages are index pages that list and link to all content in that topic area.
- **Use [[wiki links]] liberally** -- connect related pages with `[[Page Title]]` links. Every page should link to its category index and to related topics.
- **Category pages are indexes** -- a category page like "Architecture" should list all architecture-related pages with brief descriptions and links.
- **Merge duplicates aggressively** -- if two pages cover the same topic, merge them into one. Keep the better title.
- **Delete noise** -- skip events with no lasting value. Routine tool calls, trivial status checks, and ephemeral debugging sessions are not worth persisting.
- **Keep content concise** -- write summaries, not transcripts. Extract the key decisions, findings, and knowledge. A wiki page should be scannable in 30 seconds.
- **Preserve attribution** -- note which agent or session produced the information when relevant (e.g., "Discovered during session X" or "Reported by agent Y").
- **Date-stamp updates** -- when updating a page, add a date marker so readers know when information was added.
