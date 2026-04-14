---
name: search
description: "Search across all Octopus resources -- history events, wiki pages, and tables -- and synthesize an answer."
---

# Octopus Search

Search across all Octopus resources in a workspace and synthesize an answer with citations.

## Steps

1. **Get the question**: Use the skill invocation argument as the search query. If no argument was provided, ask the user what they want to find.

2. **Load config**: Run `octopus config --json` to get `default_workspace` and `default_store`. If not set, ask the user for workspace_id.

3. **Discover resources**: List what is available in the workspace:
   ```bash
   octopus history list --ws <workspace_id> --json
   octopus notebooks list --ws <workspace_id> --json
   octopus tables list --ws <workspace_id> --json
   ```

4. **Search across resources**:

   - **History stores**: For each history store, run full-text search:
     ```bash
     octopus history search --ws <workspace_id> --store <store_id> "query" --json
     ```

   - **Notebooks**: For each notebook, list pages and search by title/content. If the MCP server is available, use semantic search. Otherwise, list pages and read the most relevant ones:
     ```bash
     octopus notebooks pages <notebook_id> --ws <workspace_id> --json
     octopus notebooks read-page <notebook_id> <page_id> --ws <workspace_id> --json
     ```

   - **Tables**: For each table, search rows:
     ```bash
     octopus tables search <table_id> "query" --ws <workspace_id> --json
     ```

5. **Read the most relevant results in full**: For the top results from each source, read the full content to get complete context. For history events, this means reading the full event. For wiki pages, read the full page content. For table rows, examine the full row data.

6. **Synthesize an answer**: Combine the information from all sources into a clear, concise answer. Always cite your sources:
   - For history events: cite the store name, agent name, and timestamp
   - For wiki pages: cite the notebook name and page title
   - For table rows: cite the table name and relevant column values

7. **Present the answer**: Show the synthesized answer to the user with clearly marked citations. If the search returned no relevant results, say so and suggest alternative queries.

## Guidelines

- Search broadly first, then narrow down. Cast a wide net across all resource types.
- Prefer recent information over old when there are conflicts.
- If multiple sources agree, note the consensus. If they disagree, highlight the discrepancy.
- Keep the synthesized answer concise -- a few paragraphs at most. Link to specific pages/events for deeper reading.
- If the query is ambiguous, search for multiple interpretations and present the most likely one first.
