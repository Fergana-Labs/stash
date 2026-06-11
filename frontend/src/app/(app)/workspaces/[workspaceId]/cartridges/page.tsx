"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  CardGridSkeleton,
  StashesGridSkeleton,
} from "../../../../../components/SkeletonStates";
import { PinIcon, StashIcon } from "../../../../../components/StashIcons";
import CartridgeCard, {
  VIS_COLOR,
  VisibilityBadge,
} from "../../../../../components/cartridge/CartridgeCard";
import ForkCartridgeCardButton from "../../../../../components/cartridge/ForkCartridgeCardButton";
import { SelectBox } from "../../../../../components/workspace/file-browser/ItemsList";
import { useShareModal } from "../../../../../lib/shareModalContext";
import {
  addExternalCartridge,
  ApiError,
  API_BASE,
  deleteCartridge,
  dismissCartridgeInvite,
  displayVisibility,
  listCartridgeInvites,
  listStashes,
  type CartridgeInvite,
  type PublicCartridgeCard,
  type WorkspaceCartridge,
} from "../../../../../lib/api";
import { usePins } from "../../../../../lib/pins";
import { stashSlugFromInput } from "../../../../../lib/cartridgeLinks";

type ViewKey = "grid" | "list";
// The primary axis: which set of Cartridges you're looking at. Yours and Shared
// share the view toggle / quick-access; Discover is its own public-library
// surface. Each row carries its own Private/Shared/Public badge — there's no
// visibility filter to learn.
type Tab = "yours" | "shared" | "discover";

const VIEW_STORAGE_KEY = "stash_stashes_view";

const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

const TAB_COPY: Record<Tab, string> = {
  yours:
    "Cartridges you created in this workspace. Share them with people or publish them to the public library.",
  shared: "Cartridges other people created and shared with you, plus pending invites.",
  discover: "Public cartridges from the community — fork one into your workspace.",
};

export default function WorkspaceStashesPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const shareModal = useShareModal();
  const shareVersion = shareModal.version;
  const pins = usePins("cartridges", workspaceId);

  const [cartridges, setStashes] = useState<WorkspaceCartridge[] | null>(null);
  const [invites, setInvites] = useState<CartridgeInvite[]>([]);
  const [busyInviteId, setBusyInviteId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("yours");
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
      setError(e instanceof Error ? e.message : "Failed to load Cartridges");
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load, shareVersion]);

  // Pending invites are Cartridges others shared directly with you — surfaced in
  // the "Shared with you" section. Non-critical: failure leaves the list empty.
  useEffect(() => {
    listCartridgeInvites()
      .then(setInvites)
      .catch(() => setInvites([]));
  }, [shareVersion]);

  async function dismissInvite(invite: CartridgeInvite) {
    setBusyInviteId(invite.id);
    try {
      await dismissCartridgeInvite(invite.id);
      setInvites((current) => current.filter((item) => item.id !== invite.id));
    } finally {
      setBusyInviteId(null);
    }
  }

  const visible = useMemo(() => {
    if (!cartridges) return [];
    return [...cartridges].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
  }, [cartridges]);

  const native = useMemo(() => visible.filter((s) => !s.is_external), [visible]);
  const forked = useMemo(() => visible.filter((s) => s.is_external), [visible]);

  const pinnedStashes = useMemo(
    () => (cartridges ?? []).filter((s) => pins.pinnedSet.has(s.id)),
    [cartridges, pins.pinnedSet]
  );
  const recentStashes = useMemo(
    () =>
      (cartridges ?? [])
        .filter((s) => !pins.pinnedSet.has(s.id))
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 6),
    [cartridges, pins.pinnedSet]
  );

  const selectedStashes = (cartridges ?? []).filter((s) => selectedIds.has(s.id));

  async function bulkDeleteStashes() {
    if (selectedStashes.length === 0) return;
    const yes = window.confirm(
      `Delete ${selectedStashes.length} Stash${selectedStashes.length === 1 ? "" : "es"}? This can't be undone.`,
    );
    if (!yes) return;
    try {
      for (const stash of selectedStashes) {
        await deleteCartridge(stash.id);
      }
      clearSelection();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (cartridges === null) {
    return <StashesGridSkeleton />;
  }

  const isPinned = (s: WorkspaceCartridge) => pins.pinnedSet.has(s.id);

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1120px] px-12 pb-20 pt-8">
        <div className="flex items-center justify-between gap-4">
          <h1 className="m-0 font-display text-[21px] font-bold tracking-tight text-foreground">
            Cartridges
          </h1>
          <button
            type="button"
            onClick={() => shareModal.open({ workspaceId })}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-brand-600)] px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
          >
            <PlusGlyph /> New Cartridge
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {/* The primary selector: Yours / Shared with you / Discover. */}
        <CartridgeTabs
          tab={tab}
          onChange={setTab}
          yoursCount={(cartridges ?? []).filter((s) => !s.is_external).length}
          sharedCount={
            (cartridges ?? []).filter((s) => s.is_external).length + invites.length
          }
        />
        <p className="mt-2 text-[12.5px] text-muted">{TAB_COPY[tab]}</p>

        {/* Quick-access + the view toolbar belong to your held Cartridges, so
            they sit under Yours and Shared, not Discover. */}
        {tab !== "discover" && (pinnedStashes.length > 0 || recentStashes.length > 0) && (
          <CartridgeQuickAccess
            pinned={pinnedStashes}
            recent={recentStashes}
            isPinned={isPinned}
            onTogglePin={(s) => pins.toggle(s.id)}
          />
        )}

        {tab !== "discover" && (
          <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
            <CartridgeViewToggle view={view} onChange={setViewPersisted} />
          </div>
        )}

        {tab === "yours" && (
          <div className="mt-4">
            {native.length > 0 ? (
              <CartridgeCollection
                cartridges={native}
                startIndex={0}
                view={view}
                isPinned={isPinned}
                onTogglePin={(s) => pins.toggle(s.id)}
                selectedIds={selectedIds}
                onToggleSelect={toggleSelect}
                embedded
              />
            ) : (
              <EmptyHint>No cartridges yet.</EmptyHint>
            )}
          </div>
        )}

        {tab === "shared" && (
          <div className="mt-4">
            {invites.length > 0 && (
              <div className="overflow-hidden rounded-xl border border-border bg-surface">
                {invites.map((invite) => (
                  <SharedInviteRow
                    key={invite.id}
                    invite={invite}
                    busy={busyInviteId === invite.id}
                    onDismiss={() => void dismissInvite(invite)}
                  />
                ))}
              </div>
            )}
            {forked.length > 0 ? (
              <CartridgeCollection
                cartridges={forked}
                startIndex={native.length}
                view={view}
                isPinned={isPinned}
                onTogglePin={(s) => pins.toggle(s.id)}
                selectedIds={selectedIds}
                onToggleSelect={toggleSelect}
                embedded
                className={invites.length > 0 ? "mt-3" : undefined}
              />
            ) : (
              invites.length === 0 && <EmptyHint>Nothing shared with you yet.</EmptyHint>
            )}
            <ExternalCartridgeLinkForm workspaceId={workspaceId} onAdded={() => void load()} />
          </div>
        )}

        {tab === "discover" && <DiscoverSection workspaceId={workspaceId} />}
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

function ExternalCartridgeLinkForm({
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
      setError("Paste a Stash URL like /cartridges/product-plan or a Stash slug.");
      setMessage("");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      const stash = await addExternalCartridge(slug, workspaceId);
      setInput("");
      setMessage(
        stash.is_external
          ? `Added ${stash.title} to this workspace.`
          : `${stash.title} is already in this workspace.`
      );
      onAdded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add cartridge");
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
            Add external cartridge by link
          </label>
          <input
            id="external-stash-link"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="https://.../cartridges/product-plan"
            className="mt-1 w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-md bg-[var(--color-brand-600)] px-3 py-2 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-45 sm:mt-6"
        >
          {busy ? "Adding…" : "Add Cartridge"}
        </button>
      </div>
      {error ? <p className="mt-2 text-[12px] text-red-500">{error}</p> : null}
      {message ? <p className="mt-2 text-[12px] text-muted">{message}</p> : null}
    </form>
  );
}

function PlusGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

// The primary selector as an underline tab bar. Yours/Shared carry a live count;
// Discover is the public library (no owned count).
function CartridgeTabs({
  tab,
  onChange,
  yoursCount,
  sharedCount,
}: {
  tab: Tab;
  onChange: (next: Tab) => void;
  yoursCount: number;
  sharedCount: number;
}) {
  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "yours", label: "Yours", count: yoursCount },
    { key: "shared", label: "Shared with you", count: sharedCount },
    { key: "discover", label: "Discover" },
  ];
  return (
    <div className="mt-5 flex gap-1 border-b border-border">
      {tabs.map((t) => {
        const active = tab === t.key;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={
              "-mb-px border-b-2 px-3 py-2 text-[13px] transition-colors " +
              (active
                ? "border-[var(--color-brand-600)] font-semibold text-foreground"
                : "border-transparent text-muted hover:text-foreground")
            }
          >
            {t.label}
            {t.count !== undefined && (
              <span className="ml-1.5 text-[11px] text-muted">{t.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted">
      {children}
    </p>
  );
}

// A pending invite rendered as a drive-style row above the shared list. View
// opens the Cartridge; Dismiss removes the invite (the access stays — it can
// still be reached by link). Mirrors the dismiss logic in CartridgeInviteCenter.
function SharedInviteRow({
  invite,
  busy,
  onDismiss,
}: {
  invite: CartridgeInvite;
  busy: boolean;
  onDismiss: () => void;
}) {
  return (
    <div
      className="grid items-center gap-3 border-b border-border-subtle px-4 py-2 text-[13px] last:border-b-0"
      style={{ gridTemplateColumns: "minmax(0,2fr) minmax(0,1fr) auto" }}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center text-[var(--color-brand-600)]">
          <StashIcon />
        </span>
        <span className="min-w-0 truncate font-medium text-foreground">
          {invite.cartridge_title}
        </span>
        <span className="shrink-0 rounded-full border border-border bg-base px-1.5 py-0.5 font-mono text-[9.5px] text-muted">
          INVITE
        </span>
      </div>
      <span className="truncate text-[12px] text-muted">
        from {invite.invited_by_display_name} · {invite.source_workspace_name}
      </span>
      <div className="flex items-center justify-end gap-1.5">
        <button
          type="button"
          disabled={busy}
          onClick={onDismiss}
          className="rounded-md border border-border-subtle px-2 py-1 text-[12px] text-muted hover:text-foreground disabled:opacity-50"
        >
          Dismiss
        </button>
        <Link
          href={`/cartridges/${invite.cartridge_slug}`}
          className="rounded-md bg-[var(--color-brand-600)] px-2 py-1 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
        >
          View
        </Link>
      </div>
    </div>
  );
}

// --- Discover (public library), inline ---

const DISCOVER_SORTS = ["trending", "newest", "popular"] as const;
type DiscoverSort = (typeof DISCOVER_SORTS)[number];

function discoverSortLabel(sort: DiscoverSort): string {
  if (sort === "popular") return "Most viewed";
  if (sort === "trending") return "Trending";
  return "Newest";
}

async function fetchPublicCartridges(params: {
  q?: string;
  sort: DiscoverSort;
}): Promise<PublicCartridgeCard[]> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) qs.set(key, value);
  }
  const res = await fetch(`${API_BASE}/api/v1/discover/cartridges${qs.size ? `?${qs}` : ""}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.cartridges ?? [];
}

// The public marketplace as a section of the Cartridges page. Self-contained:
// owns its own search/sort/fetch and isn't touched by the page's visibility
// filter, view toggle, pins, or selection (those are for Cartridges you hold).
function DiscoverSection({ workspaceId }: { workspaceId: string }) {
  const [sort, setSort] = useState<DiscoverSort>("trending");
  const [query, setQuery] = useState("");
  const [cartridges, setCartridges] = useState<PublicCartridgeCard[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setFetching(true);
    const handle = setTimeout(() => {
      fetchPublicCartridges({ q: query || undefined, sort })
        .then((list) => {
          if (!cancelled) setCartridges(list);
        })
        .finally(() => {
          if (!cancelled) setFetching(false);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [query, sort]);

  return (
    <section className="mt-4">
      <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
        <div className="mr-auto flex items-baseline gap-2">
          <span className="sys-label" style={{ fontSize: 10.5 }}>
            public library
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex w-[220px] items-center gap-2 rounded-lg border border-border bg-base px-2.5 py-1.5">
            <SearchGlyph />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search public Cartridges…"
              className="min-w-0 flex-1 border-0 bg-transparent text-[12.5px] text-foreground placeholder:text-muted focus:outline-none"
            />
          </div>
          <div className="inline-flex gap-0.5 rounded-lg border border-border bg-base p-[3px]">
            {DISCOVER_SORTS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setSort(option)}
                className={
                  "rounded-md px-2.5 py-[3px] text-[12px] " +
                  (sort === option
                    ? "bg-raised font-semibold text-foreground"
                    : "text-muted hover:text-foreground")
                }
              >
                {discoverSortLabel(option)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {fetching ? (
        <CardGridSkeleton />
      ) : cartridges.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12px] text-muted">
          No public Cartridges match.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {cartridges.map((stash, i) => {
            const trending = sort === "trending" && i < 2;
            return (
              <CartridgeCard
                key={stash.id}
                stash={{
                  id: stash.id,
                  slug: stash.slug,
                  title: stash.title,
                  description: stash.description,
                  cover_image_url: stash.cover_image_url,
                  access: "public",
                  item_count: stash.item_count,
                  updated_at: stash.updated_at,
                }}
                cover={COVERS[i % COVERS.length]}
                badge={
                  trending ? (
                    <span className="absolute left-3 top-2.5 inline-flex items-center gap-1 rounded-full bg-black/80 px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.04em] text-white">
                      ↗ trending
                    </span>
                  ) : undefined
                }
                cornerAction={
                  stash.workspace_id === workspaceId ? undefined : (
                    <ForkCartridgeCardButton
                      slug={stash.slug}
                      sourceWorkspaceId={stash.workspace_id}
                    />
                  )
                }
                footer={
                  <>
                    <span className="min-w-0 truncate">
                      {stash.owner_display_name}
                      {stash.workspace_name && (
                        <>
                          {" · "}
                          <span className="font-mono text-dim">{stash.workspace_name}</span>
                        </>
                      )}
                    </span>
                    <span className="inline-flex flex-shrink-0 items-center gap-1 rounded-md border border-border bg-base px-2 py-0.5 text-[11.5px] font-medium text-foreground group-hover:border-[var(--color-brand-300)] group-hover:bg-[var(--color-brand-50)] group-hover:text-[var(--color-brand-700)]">
                      Open →
                    </span>
                  </>
                }
              />
            );
          })}
        </div>
      )}
    </section>
  );
}

function SearchGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}


function CartridgeCollection({
  cartridges,
  startIndex,
  view,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
  embedded,
  className,
}: {
  cartridges: WorkspaceCartridge[];
  startIndex: number;
  view: ViewKey;
  isPinned: (stash: WorkspaceCartridge) => boolean;
  onTogglePin: (stash: WorkspaceCartridge) => void;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  embedded?: boolean;
  className?: string;
}) {
  const extra = className ? ` ${className}` : "";
  if (view === "list") {
    return (
      <div
        className={
          (embedded ? "" : "mt-4 ") +
          "overflow-hidden rounded-xl border border-border bg-surface" +
          extra
        }
      >
        {cartridges.map((stash) => (
          <CartridgeListRow
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
        "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" +
        extra
      }
    >
      {cartridges.map((stash, i) => (
        <CartridgeCard
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
            <CartridgePinButton
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

function CartridgeListRow({
  stash,
  pinned,
  onTogglePin,
  selected,
  onToggleSelect,
}: {
  stash: WorkspaceCartridge;
  pinned: boolean;
  onTogglePin: (stash: WorkspaceCartridge) => void;
  selected: boolean;
  onToggleSelect: (id: string) => void;
}) {
  const itemCount = stash.items?.length ?? 0;
  const author = stash.owner_display_name || stash.owner_name || "";

  return (
    <Link
      href={`/cartridges/${stash.slug}`}
      className={
        "group grid items-center gap-3 border-b border-border-subtle px-4 py-2 text-[13px] last:border-b-0 " +
        (selected ? "bg-[var(--color-brand-50)]" : "hover:bg-[var(--color-brand-50)]/50")
      }
      style={{ gridTemplateColumns: "auto minmax(0,2fr) minmax(0,1fr) auto auto" }}
    >
      <SelectBox selected={selected} onToggle={() => onToggleSelect(stash.id)} />
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center text-[var(--color-brand-600)]">
          <StashIcon />
        </span>
        <span className="min-w-0 truncate font-medium text-foreground">{stash.title}</span>
        {stash.is_external && (
          <span className="shrink-0 rounded-full border border-border bg-base px-1.5 py-0.5 font-mono text-[9.5px] text-muted">
            EXTERNAL
          </span>
        )}
      </div>
      <span className="truncate text-[12px] text-muted">
        {author && `by ${author} · `}
        {itemCount} item{itemCount === 1 ? "" : "s"}
        {stash.updated_at && ` · ${relativeTime(stash.updated_at)}`}
      </span>
      <VisibilityBadge access={stash.access} shareCount={stash.share_count} />
      <span
        className={
          pinned
            ? ""
            : "opacity-0 transition focus-within:opacity-100 group-hover:opacity-100"
        }
      >
        <CartridgePinButton pinned={pinned} onToggle={() => onTogglePin(stash)} />
      </span>
    </Link>
  );
}

// Pin toggle reused on stash cards (over the cover), list rows, and the
// quick-access strip. Stops the click from following the card/row link.
function CartridgePinButton({
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

function CartridgeQuickAccess({
  pinned,
  recent,
  isPinned,
  onTogglePin,
}: {
  pinned: WorkspaceCartridge[];
  recent: WorkspaceCartridge[];
  isPinned: (stash: WorkspaceCartridge) => boolean;
  onTogglePin: (stash: WorkspaceCartridge) => void;
}) {
  return (
    <div className="mt-5 space-y-4">
      {pinned.length > 0 && (
        <QuickAccessRow title="Pinned">
          {pinned.map((stash) => (
            <CartridgeQuickCard
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
            <CartridgeQuickCard
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

function CartridgeQuickCard({
  stash,
  pinned,
  onTogglePin,
}: {
  stash: WorkspaceCartridge;
  pinned: boolean;
  onTogglePin: (stash: WorkspaceCartridge) => void;
}) {
  const dotColor = VIS_COLOR[displayVisibility(stash.access, stash.share_count)];
  return (
    <Link
      href={`/cartridges/${stash.slug}`}
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
        <CartridgePinButton pinned={pinned} onToggle={() => onTogglePin(stash)} />
      </span>
    </Link>
  );
}

function CartridgeViewToggle({
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
