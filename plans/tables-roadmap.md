# Tables roadmap: closing the Notion / AFFiNE gap

Where Stash tables stand today vs. Notion databases and AFFiNE's data-view,
and the work we'd need to close the gap. Companion to the bug-fix PR that
landed the CSV parser fix, Sheets type inference, and Notion partial-import
handling — those were _correctness_ fixes; this is the _feature_ plan.

## Today

- Storage: `tables` + `table_rows` (JSONB) in Postgres. 10 column types:
  text, number, boolean, date, datetime, url, email, select, multiselect,
  json. Validation in `backend/services/row_validation.py`.
- Views: single grid (`frontend/src/app/tables/[tableId]/page.tsx`).
  Saved-layout persists hidden cols + sort + filters.
- Filtering/sort/group: 9 ops, single-column sort, in-memory group-by
  (text/select only; not persisted in saved layouts).
- Imports: CSV (server `ingest-csv` + in-place table-page import), Google
  Docs → markdown, Google Sheets → table (first tab), Notion DB → table,
  Notion pages → pages, PPTX → slides, GitHub repo → folder.
- Exports: CSV only.

## What's missing — ranked by leverage

### Tier 1 — high-leverage, low-cost

1. **TSV paste from Excel / Sheets / Notion** into the grid. ~30 LOC. The
   single biggest UX gap relative to Notion ("copy a block of cells and
   paste"). Reuses `parseCsv` (swap `,` delimiter for `\t`) + the existing
   batch-row endpoint. Land before any new view.

2. **Drag-and-drop CSV onto the table grid.** Same handler; replaces the
   `Import` button as the primary affordance.

3. **Column-type change post-import.** UI already exists to set type at
   create-time (`COLUMN_TYPES` dropdown) but there's no "change type" path
   on an existing column. Backend `update_column` already supports it —
   wire it through the column header menu. Closes the loop on bad type
   inference from CSV/Sheets.

4. **XLSX → table.** UI already advertises `.xlsx` in
   `EditorToolbar.tsx:307`. Add `openpyxl` server-side and a
   `/files/{id}/ingest-xlsx` endpoint mirroring `ingest-csv`. Each sheet
   → one table (named `<filename> — <sheet>`). Probably the most-asked
   import format we don't support.

5. **Multi-tab Sheets import.** Today only the first tab imports;
   silently. Hit `spreadsheets.get` (Sheets API) to enumerate sheets,
   then one table per tab. Same shape as XLSX above — the importer task
   loop just iterates tabs instead of files.

### Tier 2 — alternate views

Stash has one view (grid). Notion has six; AFFiNE ships three
(table/kanban/calendar). Grouping logic already exists; views mostly
re-render the same `groupedRows`/`filteredRows` source-of-truth.

6. **Kanban view.** Re-render `groupedRows` as columns of cards instead of
   collapsed table sections. Drag-card-to-column = `updateRow` with new
   group-by value. Only meaningful on `select` columns. ~1–2 days.

7. **Calendar view.** Render rows on a month grid keyed by a `date` or
   `datetime` column. Drag-card-to-day = `updateRow`. Month-only for v1
   (no week/agenda). ~3 days.

8. **Gallery view.** Card-per-row with a cover image. Requires a new
   `image` column type (see Tier 3), so dependent.

Views need a `kind` discriminator on the saved view payload
(`backend/services/table_service.py:save_view`). Currently views only
encode filter/sort/hidden state — adding `view_kind: "grid" | "kanban" |
"calendar"` is a forward-compatible JSON field.

### Tier 3 — new column types

Notion has ~25 property types; we have 10. The high-leverage ones we
don't:

9. **Image / file attachment column.** Storage already exists via
   `files_service`; new column type stores a list of file_ids. Render as
   thumbnails in cells, full preview in row-detail. Prereq for gallery
   view.

10. **Person column.** Workspace already has users + permissions; column
    stores `user_id`. Renders as avatar + name. Mostly UI; the hard part
    is membership autocomplete.

11. **Relation column.** Foreign key to another table's row. Storage:
    `list[uuid]` of `table_rows.id`. Validation needs a join check.
    Renders as pill links. The Notion killer feature we don't have.

12. **Rollup column.** Aggregate over a `relation`. Computed at read
    time. Specs: `relation_col_id`, `target_col_id`, `agg` (count/sum/
    avg/min/max/concat). Cheap to implement once `relation` exists.

13. **Formula column.** Computed via a small expression DSL. Significant
    scope — spec, parser, evaluator, dependency graph for cache
    invalidation. Park until Tier 1–2 ship.

### Tier 4 — Notion-equivalent affordances

14. **Row-as-page.** Each row opens to a full editable doc body, same
    editor as `pages`. Storage: a `page_id` per row, lazily-created on
    first open; rendered in the detail panel. The single highest-impact
    feature we don't have — it's how Notion blurs the line between docs
    and DBs.

15. **Linked / synced views of a table** inside a page. Tiptap node
    that embeds a table by id; renders the standard grid in read-only
    mode by default, opens to the full table page on click.

16. **Re-sync from source** (Notion / Sheets / CSV-file). Store
    `source_kind` + `source_id` on the table; "Refresh from source"
    action re-runs the importer with merge semantics (match-by-primary-
    key; new rows append, missing rows soft-delete). One-shot imports
    today turn the table into a fork at import time.

17. **Realtime collab on tables.** `collab/` is wired for docs (yjs +
    hocuspocus). Tables aren't. Cell-level CRDT or row-level OT — pick
    one. Comments at row level depend on this.

18. **Notion HTML / ZIP import (no OAuth).** AFFiNE ships this in their
    `notion-html` block adapter. Users with a Notion export ZIP could
    import without setting up an integration. Strict subset of what the
    API path does, but unblocks the "I just want to try it" flow.

## Suggested sequencing

```
PR1 (this branch): correctness fixes — CSV parser, Sheets inference,
                   Notion truncation.

Phase A (≈1 week):  TSV paste, drag-drop CSV, column-type change post-
                    import, XLSX importer, multi-tab Sheets.
                    [Tier 1: items 1-5]

Phase B (≈2 weeks): kanban view + calendar view + view_kind on saved
                    views + image column + gallery view.
                    [Tier 2 + image dep from Tier 3]

Phase C (≈3 weeks): person + relation + rollup columns.
                    [Tier 3 minus formula]

Phase D (open):     row-as-page (highest UX leverage but largest scope),
                    re-sync, linked views, formula columns, realtime
                    collab, Notion HTML import.
                    [Tier 4]
```

## Non-goals (for now)

- Pivot tables / cross-tab aggregations beyond the existing summary row.
- Gantt / timeline view.
- Sub-items / hierarchical rows.
- Button / automation columns.
- AI autofill of empty cells (we have ask-the-stash; "autofill column X
  from rows" is a follow-on, not in scope here).
- Conditional formatting beyond the existing hard-coded quartile
  coloring.

## Schema notes

The current `table.columns` field is a JSONB list of column descriptors;
adding new types (image, person, relation, rollup) doesn't require a
migration — just new `type` values plus matching branches in
`row_validation._coerce` and the frontend renderer. Same for views:
`table.views` is already JSONB.

Two cases _do_ need migrations:

- **Row-as-page**: new `table_row_pages` table mapping `row_id → page_id`,
  or a `page_id` column on `table_rows`. Column variant is simpler.
- **Source provenance for re-sync**: add `source_kind text`, `source_id
  text`, `source_synced_at timestamptz` to `tables`. ~1 migration.

Everything else fits inside existing JSONB.
