/**
 * RFC-4180 CSV parser + column-type inference.
 *
 * Mirrors the server-side type detection in `backend/routers/files.py`
 * (`_infer_column_type`) so a CSV imported into an existing table from the
 * table page lands with the same column types as one imported into a brand-new
 * table via /files/{id}/ingest-csv. Values themselves are coerced server-side
 * by `row_validation.py`, so we ship raw strings (or `null` for empties).
 */

export type InferredType =
  | "boolean"
  | "number"
  | "date"
  | "datetime"
  | "text";

export function parseCsv(text: string): string[][] {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);

  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      field += ch;
      i++;
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
      i++;
      continue;
    }
    if (ch === ",") {
      row.push(field);
      field = "";
      i++;
      continue;
    }
    if (ch === "\r") {
      row.push(field);
      field = "";
      rows.push(row);
      row = [];
      if (text[i + 1] === "\n") i += 2;
      else i++;
      continue;
    }
    if (ch === "\n") {
      row.push(field);
      field = "";
      rows.push(row);
      row = [];
      i++;
      continue;
    }
    field += ch;
    i++;
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  while (
    rows.length > 0 &&
    rows[rows.length - 1].length === 1 &&
    rows[rows.length - 1][0] === ""
  ) {
    rows.pop();
  }
  return rows;
}

const NUMERIC_RE = /^-?\$?[\d,]+(\.\d+)?%?$/;
const DATE_RE =
  /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?)?$/;
const BOOL_VALUES = new Set([
  "true",
  "false",
  "yes",
  "no",
  "y",
  "n",
  "0",
  "1",
]);

export function inferColumnType(samples: string[]): InferredType {
  const nonempty = samples.filter((s) => s !== "");
  if (nonempty.length === 0) return "text";
  if (nonempty.every((s) => BOOL_VALUES.has(s.toLowerCase()))) return "boolean";
  if (nonempty.every((s) => NUMERIC_RE.test(s))) return "number";
  if (nonempty.every((s) => DATE_RE.test(s))) {
    return nonempty.every((s) => s.includes("T")) ? "datetime" : "date";
  }
  return "text";
}
