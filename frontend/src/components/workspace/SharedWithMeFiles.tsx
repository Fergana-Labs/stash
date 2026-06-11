"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listSharedWithMe, type SharedWithMeItem } from "../../lib/api";
import { KindIcon, tintFor, type ItemKind } from "./file-browser/kind";

// Shared folders/pages/files/tables surfaced inside the Files source. Session
// folders are handled in the Agent Sessions view, not here.
const FILE_KINDS = new Set<SharedWithMeItem["object_type"]>(["folder", "page", "file", "table"]);

const ITEM_KIND: Record<string, ItemKind> = {
  folder: "folder",
  page: "page",
  file: "file",
  table: "datatable",
};
const LABEL: Record<string, string> = {
  folder: "Folder",
  page: "Page",
  file: "File",
  table: "Table",
};

// SharedWithMeItem has no updated_at, so the columns are Name / Shared by /
// Type rather than the main list's Name / Modified / Type.
const GRID_COLS = "minmax(0,2fr) minmax(0,1fr) minmax(0,1fr)";

function hrefFor(item: SharedWithMeItem): string {
  const ws = item.workspace_id;
  if (item.object_type === "page") return `/p/${item.object_id}`;
  if (item.object_type === "file") return `/f/${item.object_id}`;
  if (item.object_type === "table") return `/tables/${item.object_id}`;
  return `/workspaces/${ws}/folders/${item.object_id}`;
}

export default function SharedWithMeFiles() {
  const [items, setItems] = useState<SharedWithMeItem[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    listSharedWithMe()
      .then((all) => setItems(all.filter((i) => FILE_KINDS.has(i.object_type))))
      .catch(() => setItems([]))
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) return null;

  if (items.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted">
        Nothing shared with you yet. Folders, pages, files, and tables others
        share with you show up here.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <div
        className="grid items-center gap-3 border-b border-border bg-base/60 px-4 py-2.5 text-[11px] font-medium uppercase tracking-wide text-muted"
        style={{ gridTemplateColumns: GRID_COLS }}
      >
        <span>Name</span>
        <span>Shared by</span>
        <span>Type</span>
      </div>
      {items.map((item) => {
        const kind = ITEM_KIND[item.object_type];
        return (
          <Link
            key={`${item.object_type}:${item.object_id}`}
            href={hrefFor(item)}
            className="grid items-center gap-3 border-b border-border-subtle px-4 py-2 text-[13px] last:border-b-0 hover:bg-[var(--color-brand-50)]/50"
            style={{ gridTemplateColumns: GRID_COLS }}
          >
            <div className="flex min-w-0 items-center gap-2.5">
              <span
                className={
                  "flex h-4 w-4 flex-shrink-0 items-center justify-center " +
                  tintFor({ kind, id: item.object_id, name: item.name, subtitle: "" })
                }
              >
                <KindIcon kind={kind} />
              </span>
              <span className="min-w-0 truncate font-medium text-foreground">{item.name}</span>
            </div>
            <span className="truncate text-[12px] text-muted">
              {item.shared_by || "—"}
            </span>
            <span className="flex items-center gap-2 text-[12px] text-muted">
              {LABEL[item.object_type]}
              {item.permission === "write" && (
                <span className="rounded bg-raised px-1.5 py-0.5 text-[10.5px] uppercase tracking-wide">
                  can edit
                </span>
              )}
            </span>
          </Link>
        );
      })}
    </div>
  );
}
