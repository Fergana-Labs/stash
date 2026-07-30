"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, FileText, Plus, X } from "lucide-react";

import { setRowTopics, updateTableRow } from "@/lib/api";
import type { MiniProgramManifest, Table, TableColumn, TableRow } from "@/lib/types";

import TopicInput from "./TopicInput";
import { cellLabels, cellText, internalPath } from "./cells";

function inputValue(row: TableRow, column: TableColumn): string {
  const value = row.data[column.id];
  if (value == null) return "";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function parsedValue(column: TableColumn, value: string): unknown {
  if (column.type === "number") return value === "" ? null : Number(value);
  if (column.type === "boolean") return value === "true";
  if (column.type === "multiselect") {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return value;
}

function FieldInput({
  column,
  value,
  onChange,
}: {
  column: TableColumn;
  value: string;
  onChange: (value: string) => void;
}) {
  if (column.type === "select") {
    return (
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-border bg-base px-2.5 py-2 text-[12.5px] text-foreground"
      >
        <option value="">—</option>
        {(column.options ?? []).map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  if (column.type === "boolean") {
    return (
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-border bg-base px-2.5 py-2 text-[12.5px] text-foreground"
      >
        <option value="false">No</option>
        <option value="true">Yes</option>
      </select>
    );
  }

  if (column.name === "Summary") {
    return (
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={5}
        className="w-full resize-y rounded-md border border-border bg-base px-2.5 py-2 text-[12.5px] leading-relaxed text-foreground"
      />
    );
  }

  return (
    <input
      type={column.type === "number" ? "number" : column.type === "url" ? "url" : "text"}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-md border border-border bg-base px-2.5 py-2 text-[12.5px] text-foreground"
    />
  );
}

export default function AppDetail({
  row,
  slug,
  manifest,
  table,
  knownTopics,
  onClose,
  onChanged,
}: {
  row: TableRow;
  slug: string;
  manifest: MiniProgramManifest;
  table: Table;
  knownTopics: string[];
  onClose: () => void;
  onChanged: () => Promise<void> | void;
}) {
  const columns = useMemo(
    () => [...table.columns].sort((a, b) => a.order - b.order),
    [table.columns]
  );
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [addingTopic, setAddingTopic] = useState(false);
  const [saving, setSaving] = useState(false);

  const labelColumnId = manifest.detail.labels;
  const labels = cellLabels(row, labelColumnId);
  const title = cellText(row, manifest.detail.title) || "Untitled";

  // The two things a saved item is *for*: the copy we captured, and where it
  // came from. The Clip cell holds an absolute app URL, which may point at a
  // different origin than the one being browsed, so it's reduced to a path.
  const archivedPath = internalPath(cellText(row, manifest.detail.content));
  const originalUrl = cellText(row, manifest.detail.link);

  useEffect(() => {
    setValues(
      Object.fromEntries(columns.map((column) => [column.id, inputValue(row, column)]))
    );
    setError("");
    setAddingTopic(false);
  }, [row, columns]);

  const saveTopics = async (next: string[]) => {
    setSaving(true);
    setError("");
    try {
      await setRowTopics(slug, row.id, next);
      setAddingTopic(false);
      await onChanged();
    } catch {
      setError("Couldn't save topics.");
    } finally {
      setSaving(false);
    }
  };

  const saveFields = async () => {
    const changes: Record<string, unknown> = {};
    for (const column of columns) {
      if (column.id === labelColumnId) continue;
      const next = parsedValue(column, values[column.id] ?? "");
      const current = row.data[column.id] ?? "";
      if (JSON.stringify(next) !== JSON.stringify(current)) changes[column.id] = next;
    }

    if (Object.keys(changes).length === 0) return;

    setSaving(true);
    setError("");
    try {
      await updateTableRow(table.id, row.id, changes);
      await onChanged();
    } catch {
      setError("Couldn't save changes.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <aside
      data-testid="app-detail"
      className="fixed inset-y-0 left-[74px] right-0 z-30 flex w-auto flex-col border-l border-border bg-surface shadow-xl lg:relative lg:inset-auto lg:z-auto lg:h-full lg:w-auto lg:shadow-none"
    >
      <div className="flex items-start justify-between gap-2 border-b border-border px-4 py-3">
        <h2 className="min-w-0 truncate text-[14px] font-semibold text-foreground">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close details"
          className="rounded p-1.5 text-muted-foreground hover:bg-raised hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {(archivedPath || originalUrl) && (
        <div
          data-testid="detail-links"
          className="flex flex-wrap gap-2 border-b border-border px-4 py-2.5"
        >
          {archivedPath && (
            <a
              href={archivedPath}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded border border-border px-2.5 py-1.5 text-[12px] text-foreground hover:bg-raised"
            >
              <FileText className="h-3.5 w-3.5 text-brand" />
              Open saved copy
            </a>
          )}
          {originalUrl && (
            <a
              href={originalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded border border-border px-2.5 py-1.5 text-[12px] text-foreground hover:bg-raised"
            >
              <ExternalLink className="h-3.5 w-3.5 text-brand" />
              Open original
            </a>
          )}
        </div>
      )}

      <div className="scroll-thin flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {columns.map((column) => {
          if (column.id === labelColumnId) {
            return (
              <section key={column.id} data-testid="topics-editor">
                <label className="mb-1.5 block text-[11.5px] font-medium text-muted-foreground">
                  {column.name}
                </label>
                <div className="flex flex-wrap items-center gap-1">
                  {labels.map((label) => (
                    <span
                      key={label}
                      className="inline-flex items-center gap-1 rounded bg-raised py-1 pl-2 pr-1 text-[11.5px] text-foreground"
                    >
                      {label}
                      <button
                        type="button"
                        aria-label={`Remove ${label}`}
                        disabled={saving}
                        onClick={() => saveTopics(labels.filter((item) => item !== label))}
                        className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                  {!addingTopic && (
                    <button
                      type="button"
                      onClick={() => setAddingTopic(true)}
                      data-testid="add-topic"
                      className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11.5px] text-muted-foreground hover:bg-raised hover:text-foreground"
                    >
                      <Plus className="h-3 w-3" />
                      Add topic
                    </button>
                  )}
                </div>
                {addingTopic && (
                  <div className="mt-2">
                    <TopicInput
                      knownTopics={knownTopics.filter((topic) => !labels.includes(topic))}
                      onSubmit={(topic) => saveTopics([...labels, topic])}
                      onCancel={() => setAddingTopic(false)}
                    />
                  </div>
                )}
              </section>
            );
          }

          return (
            <label key={column.id} className="block">
              <span className="mb-1.5 block text-[11.5px] font-medium text-muted-foreground">
                {column.name}
              </span>
              <FieldInput
                column={column}
                value={values[column.id] ?? ""}
                onChange={(value) =>
                  setValues((current) => ({ ...current, [column.id]: value }))
                }
              />
            </label>
          );
        })}

        {error && <p className="text-[11.5px] text-red-500">{error}</p>}
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md px-3 py-1.5 text-[12.5px] text-muted-foreground hover:bg-raised hover:text-foreground"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={saveFields}
          disabled={saving}
          className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-brand-hover disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>
    </aside>
  );
}
