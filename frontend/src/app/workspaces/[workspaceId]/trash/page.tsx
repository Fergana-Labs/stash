"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../hooks/useAuth";
import { getTrash, purgeItem, restoreItem } from "../../../../lib/api";
import type { TrashEntry, TrashKind, TrashListing } from "../../../../lib/types";

type RowKind = TrashKind;

const SECTION_TITLES: Record<RowKind, string> = {
  page: "Pages",
  file: "Files",
  session: "Sessions",
};

export default function TrashPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading } = useAuth();

  const [data, setData] = useState<TrashListing | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  useBreadcrumbs([{ label: "Trash" }], `${workspaceId}/trash`);

  const load = useCallback(async () => {
    try {
      setData(await getTrash(workspaceId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load trash");
    }
  }, [workspaceId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  async function handleRestore(kind: RowKind, id: string) {
    setBusyId(id);
    setError("");
    try {
      await restoreItem(workspaceId, kind, id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Restore failed");
    } finally {
      setBusyId(null);
    }
  }

  async function handlePurge(kind: RowKind, id: string, name: string) {
    if (!window.confirm(`Permanently delete "${name}"? This cannot be undone.`)) return;
    setBusyId(id);
    setError("");
    try {
      await purgeItem(workspaceId, kind, id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Permanent delete failed");
    } finally {
      setBusyId(null);
    }
  }

  if (loading || !data)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  const total = data.pages.length + data.files.length + data.sessions.length;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-12 py-8">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
            Trash
          </h1>
          <span className="sys-label" style={{ fontSize: 10.5 }}>
            {total} item{total === 1 ? "" : "s"}
          </span>
        </div>

        <p className="mt-2 text-[13px] text-muted">
          Items here are recoverable. Permanent delete cannot be undone.
        </p>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        <div className="mt-6 flex flex-col gap-6">
          {(["page", "file", "session"] as const).map((kind) => (
            <TrashSection
              key={kind}
              title={SECTION_TITLES[kind]}
              kind={kind}
              entries={data[`${kind}s`]}
              busyId={busyId}
              onRestore={handleRestore}
              onPurge={handlePurge}
            />
          ))}
          {total === 0 && (
            <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-8 text-center text-[12.5px] text-muted">
              Nothing in trash.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TrashSection({
  title,
  kind,
  entries,
  busyId,
  onRestore,
  onPurge,
}: {
  title: string;
  kind: RowKind;
  entries: TrashEntry[];
  busyId: string | null;
  onRestore: (kind: RowKind, id: string) => void;
  onPurge: (kind: RowKind, id: string, name: string) => void;
}) {
  if (entries.length === 0) return null;
  return (
    <section>
      <h2 className="mb-2 font-display text-[15px] font-semibold text-foreground">
        {title} <span className="text-muted">({entries.length})</span>
      </h2>
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        {entries.map((entry) => (
          <div
            key={entry.id}
            className="flex items-center gap-3 border-b border-border px-4 py-2.5 text-[13px] last:border-b-0"
          >
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium text-foreground">{entry.name}</div>
              <div className="mt-0.5 truncate text-[11.5px] text-muted">
                Deleted {formatRelative(entry.deleted_at)}
                {entry.deleted_by_name ? ` by ${entry.deleted_by_name}` : ""}
              </div>
            </div>
            <button
              type="button"
              disabled={busyId === entry.id}
              onClick={() => onRestore(kind, entry.id)}
              className="rounded-md border border-border bg-base px-3 py-1 text-[12px] text-foreground hover:bg-raised disabled:opacity-50"
            >
              Restore
            </button>
            <button
              type="button"
              disabled={busyId === entry.id}
              onClick={() => onPurge(kind, entry.id, entry.name)}
              className="rounded-md border border-red-300/60 bg-red-500/5 px-3 py-1 text-[12px] text-red-600 hover:bg-red-500/10 disabled:opacity-50"
            >
              Delete forever
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatRelative(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return new Date(iso).toLocaleDateString();
}
