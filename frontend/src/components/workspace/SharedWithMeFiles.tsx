"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listSharedWithMe, type SharedWithMeItem } from "../../lib/api";

// Shared folders/pages/files/tables surfaced inside the Files source. Session
// folders are handled in the Agent Sessions view, not here.
const FILE_KINDS = new Set<SharedWithMeItem["object_type"]>(["folder", "page", "file", "table"]);

const ICON: Record<string, string> = {
  folder: "📁",
  page: "📄",
  file: "📎",
  table: "▦",
};
const LABEL: Record<string, string> = {
  folder: "Folder",
  page: "Page",
  file: "File",
  table: "Table",
};

function hrefFor(item: SharedWithMeItem): string {
  const ws = item.workspace_id;
  if (item.object_type === "page") return `/workspaces/${ws}/p/${item.object_id}`;
  if (item.object_type === "file") return `/workspaces/${ws}/f/${item.object_id}`;
  if (item.object_type === "table") return `/tables/${item.object_id}?workspaceId=${ws}`;
  return `/workspaces/${ws}/folders/${item.object_id}`;
}

export default function SharedWithMeFiles() {
  const [items, setItems] = useState<SharedWithMeItem[]>([]);

  useEffect(() => {
    listSharedWithMe()
      .then((all) => setItems(all.filter((i) => FILE_KINDS.has(i.object_type))))
      .catch(() => setItems([]));
  }, []);

  if (items.length === 0) return null;

  return (
    <section className="mt-8">
      <h2 className="m-0 mb-2 px-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
        Shared with me
      </h2>
      <div className="space-y-1.5">
        {items.map((item) => (
          <Link
            key={`${item.object_type}:${item.object_id}`}
            href={hrefFor(item)}
            className="flex items-center gap-3 rounded-lg border border-border bg-surface/40 px-4 py-3 hover:bg-raised/40"
          >
            <span aria-hidden>{ICON[item.object_type]}</span>
            <span className="flex-1 truncate text-[13.5px] font-medium text-foreground">
              {item.name}
            </span>
            {item.shared_by ? (
              <span className="text-[11.5px] text-muted">from {item.shared_by}</span>
            ) : null}
            {item.permission === "write" ? (
              <span className="rounded bg-raised px-1.5 py-0.5 text-[10.5px] uppercase tracking-wide text-muted">
                can edit
              </span>
            ) : null}
            <span className="text-[12px] text-muted">{LABEL[item.object_type]}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
