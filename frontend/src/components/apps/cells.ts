import type { TableRow } from "@/lib/types";

/** Read a cell as display text. Slots are optional in a manifest and cells are
 *  untyped JSON, so every read has to tolerate a missing column id. */
export function cellText(row: TableRow, columnId: string | undefined): string {
  if (!columnId) return "";
  const value = row.data[columnId];
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

/** Read a multiselect cell as its labels. A multiselect stores an array, but a
 *  single-select column mapped into the same slot stores a bare string. */
export function cellLabels(row: TableRow, columnId: string | undefined): string[] {
  if (!columnId) return [];
  const value = row.data[columnId];
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (typeof value === "string" && value) return [value];
  return [];
}

/** Every distinct label across the loaded rows, most frequent first — the
 *  filter chips. Derived from the rows rather than the column's options so a
 *  chip never shows a topic that filters to nothing. */
export function labelFacets(rows: TableRow[], columnId: string | undefined): string[] {
  if (!columnId) return [];
  const counts = new Map<string, number>();
  for (const row of rows) {
    for (const label of cellLabels(row, columnId)) {
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([l]) => l);
}

/** An in-app link (/p/<id> or /f/<id>) for the archived copy, if the cell
 *  holds one. Clip cells store absolute URLs against PUBLIC_URL, which may
 *  differ from the origin the app is being viewed on. */
export function internalPath(value: string): string | null {
  if (!value) return null;
  const match = value.match(/\/(p|f)\/([0-9a-fA-F-]{36})\/?$/);
  return match ? `/${match[1]}/${match[2]}` : null;
}
