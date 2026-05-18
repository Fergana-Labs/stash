"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useShareModal } from "../../../../lib/shareModalContext";
import { listStashes, type WorkspaceStash } from "../../../../lib/api";

type Filter = "all" | "workspace" | "private" | "public" | "external";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "workspace", label: "Workspace" },
  { key: "private", label: "Private" },
  { key: "public", label: "Public" },
  { key: "external", label: "External" },
];

const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function WorkspaceStashesPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const shareModal = useShareModal();
  const shareVersion = shareModal.version;

  const [stashes, setStashes] = useState<WorkspaceStash[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const list = await listStashes(workspaceId);
      setStashes(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load Stashes");
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load, shareVersion]);

  const counts = useMemo(() => {
    const list = stashes ?? [];
    return {
      all: list.length,
      workspace: list.filter((s) => s.access === "workspace" && !s.is_external).length,
      private: list.filter((s) => s.access === "private").length,
      public: list.filter((s) => s.access === "public").length,
      external: list.filter((s) => s.is_external).length,
    };
  }, [stashes]);

  const filtered = useMemo(() => {
    if (!stashes) return [];
    const ordered = [...stashes].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
    if (filter === "all") return ordered;
    if (filter === "external") return ordered.filter((s) => s.is_external);
    return ordered.filter((s) => s.access === filter && !s.is_external);
  }, [stashes, filter]);

  if (stashes === null) {
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1120px] px-12 pb-20 pt-8">
        {/* Hero */}
        <div className="flex items-end justify-between gap-4">
          <div className="min-w-0">
            <p className="sys-label">All Stashes in workspace</p>
            <h1 className="mb-1 mt-1 font-display text-[34px] font-bold tracking-[-0.02em]">
              Stashes
            </h1>
            <p className="m-0 max-w-[620px] text-[13.5px] text-dim">
              Stashes bundle pages, sessions, and tables into one shareable
              surface. Privacy lives here — every item in a Stash inherits its
              permission level.
            </p>
          </div>
          <button
            type="button"
            onClick={() => shareModal.open({ workspaceId, tab: "new" })}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-brand-600)] px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
          >
            <PlusGlyph /> New Stash
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {/* Toolbar */}
        <div className="mt-5 flex items-center gap-1.5 border-b border-border pb-2.5">
          {FILTERS.map((f) => {
            const active = filter === f.key;
            const count = counts[f.key];
            return (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                className={
                  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12.5px] " +
                  (active
                    ? "bg-raised font-semibold text-foreground"
                    : "text-muted hover:text-foreground")
                }
              >
                {f.key !== "all" && <VisDot vis={f.key} />}
                {f.label}
                <span className="sys-label" style={{ fontSize: 10 }}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Grid */}
        {filtered.length === 0 ? (
          <div className="mt-12 rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted">
            {stashes.length === 0
              ? "No Stashes yet."
              : "No Stashes match this filter."}
          </div>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((stash, i) => (
              <StashCard
                key={stash.id}
                stash={stash}
                cover={COVERS[i % COVERS.length]}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StashCard({ stash, cover }: { stash: WorkspaceStash; cover: string }) {
  const itemCount = stash.items.length;
  const sessions = stash.items.filter((i) => i.object_type === "session").length;
  const pages = stash.items.filter((i) => i.object_type === "page").length;
  const visibility: "public" | "private" | "workspace" = stash.access;

  return (
    <Link
      href={`/stashes/${stash.slug}`}
      className="card group flex min-h-[260px] flex-col overflow-hidden transition hover:border-[var(--color-brand-300)]"
    >
      <div
        className={`${cover} relative h-[84px]`}
        style={
          stash.cover_image_url
            ? {
                backgroundImage: `url(${stash.cover_image_url})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }
            : undefined
        }
      >
        {stash.is_external && (
          <span className="absolute left-3 top-2.5 rounded-full border border-white/50 bg-white/70 px-2 py-0.5 font-mono text-[10.5px] text-foreground backdrop-blur">
            EXTERNAL
          </span>
        )}
        <span className="absolute right-3 top-2.5 inline-flex items-center gap-1.5 rounded-full bg-white/85 px-2 py-0.5 text-[11px] capitalize text-dim backdrop-blur">
          <VisDot vis={visibility} />
          {visibility}
        </span>
      </div>
      <div className="flex flex-1 flex-col p-4">
        <h3 className="m-0 font-display text-[17px] font-bold leading-tight tracking-[-0.015em] group-hover:text-[var(--color-brand-700)]">
          {stash.title}
        </h3>
        <p className="mt-2 line-clamp-2 text-[12.5px] leading-[1.55] text-dim">
          {stash.description || "No description."}
        </p>
        <div className="sys-label mt-2.5" style={{ fontSize: 10.5 }}>
          {itemCount} item{itemCount === 1 ? "" : "s"}
          {sessions > 0 && ` · ${sessions} session${sessions === 1 ? "" : "s"}`}
          {pages > 0 && ` · ${pages} page${pages === 1 ? "" : "s"}`} ·{" "}
          {stash.view_count} view{stash.view_count === 1 ? "" : "s"}
        </div>
        <div className="flex-1" />
        <div className="mt-3.5 flex items-center justify-between border-t border-border-subtle pt-2.5 text-[11.5px] text-muted">
          <span className="truncate">/{stash.slug}</span>
          <span className="font-mono">{relativeTime(stash.updated_at)}</span>
        </div>
      </div>
    </Link>
  );
}

function VisDot({ vis }: { vis: string }) {
  const color =
    vis === "public" ? "#22C55E" : vis === "private" ? "#9CA3AF" : "var(--color-brand-500)";
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: 999,
        background: color,
        display: "inline-block",
      }}
    />
  );
}

function PlusGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
