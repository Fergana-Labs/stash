"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { StashesGridSkeleton } from "../../../../../components/SkeletonStates";
import { PinIcon, StashIcon } from "../../../../../components/StashIcons";
import StashCard from "../../../../../components/stash/StashCard";
import { SelectBox } from "../../../../../components/workspace/file-browser/ItemsList";
import { useShareModal } from "../../../../../lib/shareModalContext";
import {
  addExternalStash,
  ApiError,
  deleteStash,
  listStashes,
  type WorkspaceStash,
} from "../../../../../lib/api";
import { usePins } from "../../../../../lib/pins";
import { stashSlugFromInput } from "../../../../../lib/stashLinks";

type Filter = "all" | "workspace" | "private" | "public" | "external";
type ViewKey = "grid" | "list";

const VIEW_STORAGE_KEY = "stash_stashes_view";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "workspace", label: "Workspace" },
  { key: "private", label: "Private" },
  { key: "public", label: "Public" },
  { key: "external", label: "External" },
];

const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

const VIS_COLOR: Record<string, string> = {
  public: "#22C55E",
  private: "#9CA3AF",
  workspace: "var(--color-brand-500)",
};

export default function WorkspaceStashesPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const shareModal = useShareModal();
  const shareVersion = shareModal.version;
  const pins = usePins("stashes", workspaceId);

  const [stashes, setStashes] = useState<WorkspaceStash[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [view, setView] = useState<ViewKey>("grid");
  const [error, setError] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  function toggleSelect(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(VIEW_STORAGE_KEY) as ViewKey | null;
    if (saved === "grid" || saved === "list") setView(saved);
  }, []);

  function setViewPersisted(next: ViewKey) {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_STORAGE_KEY, next);
    } catch {
      /* localStorage unavailable */
    }
  }

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

  const native = useMemo(
    () => filtered.filter((s) => !s.forked_from_stash_id),
    [filtered]
  );
  const forked = useMemo(
    () => filtered.filter((s) => !!s.forked_from_stash_id),
    [filtered]
  );

  const pinnedStashes = useMemo(
    () => (stashes ?? []).filter((s) => pins.pinnedSet.has(s.id)),
    [stashes, pins.pinnedSet]
  );
  const recentStashes = useMemo(
    () =>
      (stashes ?? [])
        .filter((s) => !pins.pinnedSet.has(s.id))
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 6),
    [stashes, pins.pinnedSet]
  );

  const selectedStashes = (stashes ?? []).filter((s) => selectedIds.has(s.id));

  async function bulkDeleteStashes() {
    if (selectedStashes.length === 0) return;
    const yes = window.confirm(
      `Delete ${selectedStashes.length} Stash${selectedStashes.length === 1 ? "" : "es"}? This can't be undone.`,
    );
    if (!yes) return;
    try {
      for (const stash of selectedStashes) {
        await deleteStash(stash.id);
      }
      clearSelection();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (stashes === null) {
    return <StashesGridSkeleton />;
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1120px] px-12 pb-20 pt-8">
        <div className="flex items-center justify-between gap-4">
          <h1 className="m-0 font-display text-[34px] font-bold tracking-[-0.02em]">
            Stashes
          </h1>
          <button
            type="button"
            onClick={() => shareModal.open({ workspaceId })}
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

        {(pinnedStashes.length > 0 || recentStashes.length > 0) && (
          <StashQuickAccess
            pinned={pinnedStashes}
            recent={recentStashes}
            isPinned={(s) => pins.pinnedSet.has(s.id)}
            onTogglePin={(s) => pins.toggle(s.id)}
          />
        )}

        {/* Toolbar */}
        <div className="mt-5 flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
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
          <StashViewToggle view={view} onChange={setViewPersisted} />
        </div>

        <ExternalStashLinkForm
          workspaceId={workspaceId}
          onAdded={() => {
            setFilter("external");
            void load();
          }}
        />

        {/* Grid */}
        {filtered.length === 0 ? (
          <div className="mt-12 rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted">
            {stashes.length === 0
              ? "No Stashes yet."
              : "No Stashes match this filter."}
          </div>
        ) : filter === "all" && forked.length > 0 && native.length > 0 ? (
          <>
            <StashGroup
              title="Workspace Stashes"
              stashes={native}
              startIndex={0}
              view={view}
              isPinned={(s) => pins.pinnedSet.has(s.id)}
              onTogglePin={(s) => pins.toggle(s.id)}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
            />
            <StashGroup
              title="Forked Stashes"
              stashes={forked}
              startIndex={native.length}
              view={view}
              isPinned={(s) => pins.pinnedSet.has(s.id)}
              onTogglePin={(s) => pins.toggle(s.id)}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
            />
          </>
        ) : (
          <StashCollection
            stashes={filtered}
            startIndex={0}
            view={view}
            isPinned={(s) => pins.pinnedSet.has(s.id)}
            onTogglePin={(s) => pins.toggle(s.id)}
            selectedIds={selectedIds}
            onToggleSelect={toggleSelect}
          />
        )}
      </div>

      {selectedStashes.length > 0 && (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center">
          <div className="pointer-events-auto flex items-center gap-3 rounded-lg border border-border bg-foreground px-4 py-2 text-[13px] text-background shadow-lg">
            <span className="font-medium">{selectedStashes.length} selected</span>
            <button
              type="button"
              onClick={() => void bulkDeleteStashes()}
              className="rounded-md border border-background/40 px-2 py-0.5 text-[12px] font-semibold hover:bg-background/10"
            >
              Delete
            </button>
            <button
              type="button"
              onClick={clearSelection}
              className="ml-1 text-[18px] leading-none text-background/70 hover:text-background"
              aria-label="Clear selection"
            >
              ×
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ExternalStashLinkForm({
  workspaceId,
  onAdded,
}: {
  workspaceId: string;
  onAdded: () => void;
}) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const slug = stashSlugFromInput(input);
    if (!slug) {
      setError("Paste a Stash URL like /stashes/product-plan or a Stash slug.");
      setMessage("");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      const stash = await addExternalStash(slug, workspaceId);
      setInput("");
      setMessage(
        stash.is_external
          ? `Added ${stash.title} to this workspace.`
          : `${stash.title} is already in this workspace.`
      );
      onAdded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add Stash");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mt-4 rounded-lg border border-border-subtle bg-surface px-3 py-3"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <label className="text-[12px] font-medium text-foreground" htmlFor="external-stash-link">
            Add external Stash by link
          </label>
          <input
            id="external-stash-link"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="https://.../stashes/product-plan"
            className="mt-1 w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-md bg-[var(--color-brand-600)] px-3 py-2 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-45 sm:mt-6"
        >
          {busy ? "Adding…" : "Add Stash"}
        </button>
      </div>
      {error ? <p className="mt-2 text-[12px] text-red-500">{error}</p> : null}
      {message ? <p className="mt-2 text-[12px] text-muted">{message}</p> : null}
    </form>
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


function StashGroup({
  title,
  stashes,
  startIndex,
  view,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
}: {
  title: string;
  stashes: WorkspaceStash[];
  startIndex: number;
  view: ViewKey;
  isPinned: (stash: WorkspaceStash) => boolean;
  onTogglePin: (stash: WorkspaceStash) => void;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
}) {
  return (
    <section className="mt-5">
      <div className="mb-2 flex items-baseline gap-2">
        <h2 className="m-0 font-display text-[14px] font-semibold">{title}</h2>
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {stashes.length}
        </span>
      </div>
      <StashCollection
        stashes={stashes}
        startIndex={startIndex}
        view={view}
        isPinned={isPinned}
        onTogglePin={onTogglePin}
        selectedIds={selectedIds}
        onToggleSelect={onToggleSelect}
        embedded
      />
    </section>
  );
}

function StashCollection({
  stashes,
  startIndex,
  view,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
  embedded,
}: {
  stashes: WorkspaceStash[];
  startIndex: number;
  view: ViewKey;
  isPinned: (stash: WorkspaceStash) => boolean;
  onTogglePin: (stash: WorkspaceStash) => void;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  embedded?: boolean;
}) {
  if (view === "list") {
    return (
      <div
        className={
          (embedded ? "" : "mt-4 ") +
          "overflow-hidden rounded-xl border border-border bg-surface"
        }
      >
        {stashes.map((stash) => (
          <StashListRow
            key={stash.id}
            stash={stash}
            pinned={isPinned(stash)}
            onTogglePin={onTogglePin}
            selected={selectedIds.has(stash.id)}
            onToggleSelect={onToggleSelect}
          />
        ))}
      </div>
    );
  }

  return (
    <div
      className={
        (embedded ? "" : "mt-4 ") +
        "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
      }
    >
      {stashes.map((stash, i) => (
        <StashCard
          key={stash.id}
          stash={stash}
          cover={COVERS[(startIndex + i) % COVERS.length]}
          selected={selectedIds.has(stash.id)}
          badge={
            <span className="absolute left-2.5 top-2.5 z-10">
              <SelectBox
                selected={selectedIds.has(stash.id)}
                onToggle={() => onToggleSelect(stash.id)}
              />
            </span>
          }
          cornerAction={
            <StashPinButton
              pinned={isPinned(stash)}
              onToggle={() => onTogglePin(stash)}
              onCover
            />
          }
        />
      ))}
    </div>
  );
}

function StashListRow({
  stash,
  pinned,
  onTogglePin,
  selected,
  onToggleSelect,
}: {
  stash: WorkspaceStash;
  pinned: boolean;
  onTogglePin: (stash: WorkspaceStash) => void;
  selected: boolean;
  onToggleSelect: (id: string) => void;
}) {
  const itemCount = stash.items?.length ?? 0;
  const author = stash.owner_display_name || stash.owner_name || "";
  const dotColor = stash.access ? VIS_COLOR[stash.access] : null;

  return (
    <Link
      href={`/stashes/${stash.slug}`}
      className={
        "group grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-3 border-b border-border-subtle px-4 py-3 last:border-b-0 " +
        (selected ? "bg-[var(--color-brand-50)]" : "hover:bg-[var(--color-brand-50)]/50")
      }
    >
      <SelectBox selected={selected} onToggle={() => onToggleSelect(stash.id)} />
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          {dotColor && (
            <span
              className="inline-block h-[8px] w-[8px] shrink-0 rounded-full"
              style={{ background: dotColor }}
              title={stash.access}
            />
          )}
          <span className="min-w-0 truncate font-display text-[14px] font-semibold tracking-tight text-foreground group-hover:text-[var(--color-brand-700)]">
            {stash.title}
          </span>
          {stash.is_external && (
            <span className="shrink-0 rounded-full border border-border bg-base px-1.5 py-0.5 font-mono text-[9.5px] text-muted">
              EXTERNAL
            </span>
          )}
        </div>
        <p className="mt-0.5 truncate text-[12px] text-muted">
          {stash.description || "No description."}
        </p>
      </div>
      <div className="sys-label whitespace-nowrap text-right" style={{ fontSize: 10.5 }}>
        {author && `by ${author} · `}
        {itemCount} item{itemCount === 1 ? "" : "s"}
        {stash.updated_at && ` · ${relativeTime(stash.updated_at)}`}
      </div>
      <StashPinButton pinned={pinned} onToggle={() => onTogglePin(stash)} />
    </Link>
  );
}

// Pin toggle reused on stash cards (over the cover), list rows, and the
// quick-access strip. Stops the click from following the card/row link.
function StashPinButton({
  pinned,
  onToggle,
  onCover,
}: {
  pinned: boolean;
  onToggle: () => void;
  onCover?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={pinned ? "Unpin Stash" : "Pin Stash"}
      aria-pressed={pinned}
      title={pinned ? "Unpin" : "Pin"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
      className={
        "flex h-6 w-6 items-center justify-center rounded transition " +
        (onCover
          ? "bg-white/70 backdrop-blur hover:bg-white "
          : "hover:bg-raised ") +
        (pinned
          ? "text-[var(--color-brand-600)] hover:text-[var(--color-brand-700)]"
          : onCover
            ? "text-foreground/70 hover:text-foreground"
            : "text-muted/50 hover:text-foreground")
      }
    >
      <PinIcon className="text-[15px]" />
    </button>
  );
}

function StashQuickAccess({
  pinned,
  recent,
  isPinned,
  onTogglePin,
}: {
  pinned: WorkspaceStash[];
  recent: WorkspaceStash[];
  isPinned: (stash: WorkspaceStash) => boolean;
  onTogglePin: (stash: WorkspaceStash) => void;
}) {
  return (
    <div className="mt-5 space-y-4">
      {pinned.length > 0 && (
        <QuickAccessRow title="Pinned">
          {pinned.map((stash) => (
            <StashQuickCard
              key={`pin-${stash.id}`}
              stash={stash}
              pinned
              onTogglePin={onTogglePin}
            />
          ))}
        </QuickAccessRow>
      )}
      {recent.length > 0 && (
        <QuickAccessRow title="Recent">
          {recent.map((stash) => (
            <StashQuickCard
              key={`recent-${stash.id}`}
              stash={stash}
              pinned={isPinned(stash)}
              onTogglePin={onTogglePin}
            />
          ))}
        </QuickAccessRow>
      )}
    </div>
  );
}

function QuickAccessRow({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="m-0 mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
        {title}
      </h2>
      <div className="flex flex-wrap gap-2.5">{children}</div>
    </section>
  );
}

function StashQuickCard({
  stash,
  pinned,
  onTogglePin,
}: {
  stash: WorkspaceStash;
  pinned: boolean;
  onTogglePin: (stash: WorkspaceStash) => void;
}) {
  const dotColor = stash.access ? VIS_COLOR[stash.access] : null;
  return (
    <Link
      href={`/stashes/${stash.slug}`}
      className="group/qa relative flex w-[200px] items-center gap-2.5 rounded-lg border border-border bg-surface px-3 py-2.5 transition hover:border-[var(--color-brand-300)] hover:bg-raised"
    >
      <span className="relative flex h-5 w-5 shrink-0 items-center justify-center text-[var(--color-brand-600)]">
        <StashIcon className="text-[18px]" />
        {dotColor && (
          <span
            className="absolute -bottom-0.5 -right-0.5 h-[7px] w-[7px] rounded-full ring-2 ring-surface"
            style={{ background: dotColor }}
          />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-medium text-foreground">
          {stash.title}
        </span>
        <span className="block truncate text-[10.5px] text-muted">
          {(stash.items?.length ?? 0)} item{(stash.items?.length ?? 0) === 1 ? "" : "s"}
        </span>
      </span>
      <span className="shrink-0">
        <StashPinButton pinned={pinned} onToggle={() => onTogglePin(stash)} />
      </span>
    </Link>
  );
}

function StashViewToggle({
  view,
  onChange,
}: {
  view: ViewKey;
  onChange: (next: ViewKey) => void;
}) {
  const opts: { key: ViewKey; label: string }[] = [
    { key: "grid", label: "Grid" },
    { key: "list", label: "List" },
  ];
  return (
    <div className="inline-flex gap-0.5 rounded-md border border-border bg-base p-[2px] text-[12px]">
      {opts.map((opt) => {
        const active = view === opt.key;
        return (
          <button
            key={opt.key}
            type="button"
            onClick={() => onChange(opt.key)}
            className={
              "rounded px-2 py-[3px] " +
              (active
                ? "bg-raised font-semibold text-foreground"
                : "text-muted hover:text-foreground")
            }
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

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
