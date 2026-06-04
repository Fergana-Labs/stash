"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  listSharedSessionFolderSessions,
  listSharedWithMe,
  type SharedSession,
  type SharedWithMeItem,
} from "../../../lib/api";
import { useAuth } from "../../../hooks/useAuth";
import { useBreadcrumbs } from "../../../components/BreadcrumbContext";

const TYPE_LABEL: Record<SharedWithMeItem["object_type"], string> = {
  folder: "Folder",
  session_folder: "Session folder",
  page: "Page",
  file: "File",
  table: "Table",
  session: "Session",
};

const TYPE_ICON: Record<SharedWithMeItem["object_type"], string> = {
  folder: "📁",
  session_folder: "🗂️",
  page: "📄",
  file: "📎",
  table: "▦",
  session: "💬",
};

// Folders/pages/files/tables/sessions open in their owning workspace's existing
// routes — the backend honours the share, so a non-member is let in. Session
// *folders* have no route, so they expand inline instead.
function hrefFor(item: SharedWithMeItem): string | null {
  const ws = item.workspace_id;
  switch (item.object_type) {
    case "folder":
      return `/workspaces/${ws}/folders/${item.object_id}`;
    case "page":
      return `/workspaces/${ws}/p/${item.object_id}`;
    case "file":
      return `/workspaces/${ws}/f/${item.object_id}`;
    case "table":
      return `/tables/${item.object_id}?workspaceId=${ws}`;
    case "session":
      return `/workspaces/${ws}/sessions/${item.object_id}`;
    case "session_folder":
      return null;
  }
}

function SharedSessionFolder({ item }: { item: SharedWithMeItem }) {
  const [open, setOpen] = useState(false);
  const [sessions, setSessions] = useState<SharedSession[] | null>(null);
  const [error, setError] = useState("");

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && sessions === null) {
      try {
        setSessions(await listSharedSessionFolderSessions(item.object_id));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load sessions");
      }
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface/40">
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-raised/40"
      >
        <span aria-hidden>{TYPE_ICON.session_folder}</span>
        <span className="flex-1 text-[13.5px] font-medium text-foreground">{item.name}</span>
        <span className="text-[12px] text-muted">{TYPE_LABEL.session_folder}</span>
        <span aria-hidden className="text-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open ? (
        <div className="border-t border-border px-4 py-2">
          {error ? <p className="py-2 text-[12.5px] text-rose-500">{error}</p> : null}
          {sessions === null && !error ? (
            <p className="py-2 text-[12.5px] text-muted">Loading…</p>
          ) : null}
          {sessions && sessions.length === 0 ? (
            <p className="py-2 text-[12.5px] text-muted">No sessions in this folder.</p>
          ) : null}
          {sessions?.map((s) => (
            <Link
              key={s.id}
              href={`/workspaces/${s.workspace_id}/sessions/${s.id}`}
              className="block rounded px-2 py-1.5 text-[13px] text-foreground hover:bg-raised/50"
            >
              {s.title || s.session_id}
              <span className="ml-2 text-[11.5px] text-muted">{s.agent_name}</span>
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function SharedWithMePage() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState<SharedWithMeItem[] | null>(null);
  const [error, setError] = useState("");

  useBreadcrumbs([{ label: "Shared with me" }], "shared");

  const load = useCallback(async () => {
    try {
      setItems(await listSharedWithMe());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load shared items");
    }
  }, []);

  useEffect(() => {
    if (!loading && user) load();
  }, [loading, user, load]);

  if (loading || items === null) {
    return <div className="p-8 text-[13px] text-muted">Loading…</div>;
  }

  // Group by the workspace the content lives in.
  const byWorkspace = new Map<string, SharedWithMeItem[]>();
  for (const it of items) {
    byWorkspace.set(it.workspace_id, [...(byWorkspace.get(it.workspace_id) ?? []), it]);
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="text-[20px] font-semibold text-foreground">Shared with me</h1>
      <p className="mt-1 text-[13px] text-muted">
        Folders, files, pages, tables, and sessions other people have shared with you.
      </p>

      {error ? <p className="mt-4 text-[13px] text-rose-500">{error}</p> : null}

      {items.length === 0 && !error ? (
        <div className="mt-8 rounded-lg border border-dashed border-border bg-surface/30 px-6 py-12 text-center text-[13px] text-muted">
          Nothing has been shared with you yet.
        </div>
      ) : null}

      {[...byWorkspace.values()].map((group) => {
        const { workspace_id: wsId, workspace_name: wsName, shared_by: sharedBy } = group[0];
        return (
          <section key={wsId} className="mt-6">
            <div className="px-1 pb-2 text-[12px] font-semibold uppercase tracking-wide text-muted">
              {wsName}
              {sharedBy ? (
                <span className="font-normal normal-case"> · shared by {sharedBy}</span>
              ) : null}
            </div>
            <div className="space-y-1.5">
              {group.map((item) =>
                item.object_type === "session_folder" ? (
                  <SharedSessionFolder key={item.object_id} item={item} />
                ) : (
                  <Link
                    key={`${item.object_type}:${item.object_id}`}
                    href={hrefFor(item) ?? "#"}
                    className="flex items-center gap-3 rounded-lg border border-border bg-surface/40 px-4 py-3 hover:bg-raised/40"
                  >
                    <span aria-hidden>{TYPE_ICON[item.object_type]}</span>
                    <span className="flex-1 text-[13.5px] font-medium text-foreground">
                      {item.name}
                    </span>
                    {item.permission === "write" ? (
                      <span className="rounded bg-raised px-1.5 py-0.5 text-[10.5px] uppercase tracking-wide text-muted">
                        can edit
                      </span>
                    ) : null}
                    <span className="text-[12px] text-muted">{TYPE_LABEL[item.object_type]}</span>
                  </Link>
                ),
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
