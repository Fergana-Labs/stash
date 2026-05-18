"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import AppShell from "../../../components/AppShell";
import { useBreadcrumbs } from "../../../components/BreadcrumbContext";
import AddToStashModal from "../../../components/stash/AddToStashModal";
import { useAuth } from "../../../hooks/useAuth";
import { useEscapeKey } from "../../../hooks/useEscapeKey";
import {
  ApiError,
  getPublicStash,
  updateStash,
  type PublicStashDetail,
  type PublicStashItem,
} from "../../../lib/api";
import AddToWorkspaceButton from "./AddToWorkspaceButton";

type StashItemGroup = Partial<Record<PublicStashItem["object_type"], PublicStashItem[]>>;

// Signed-in viewers see the Stash inside AppShell (sidebar + top bar) so
// navigation context is preserved. Anonymous viewers see the raw page.
function StashChrome({ data, children }: { data: PublicStashDetail | null; children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  useBreadcrumbs(
    [
      { label: "Stashes", href: "/stashes" },
      { label: data?.stash.title ?? "Stash" },
    ],
    `stash/${data?.stash.id ?? "loading"}`
  );
  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background text-muted">
        Loading Stash...
      </main>
    );
  }
  if (user) {
    return (
      <AppShell user={user} onLogout={logout}>
        {children}
      </AppShell>
    );
  }
  return <main className="min-h-screen bg-background">{children}</main>;
}

export default function StashPageClient({ slug }: { slug: string }) {
  const [data, setData] = useState<PublicStashDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getPublicStash(slug));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setData(null);
        setError("Stash not found");
      } else {
        setError(e instanceof Error ? e.message : "Failed to load Stash");
      }
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <StashChrome data={data}>
        <div className="flex min-h-[50vh] items-center justify-center text-muted">
          Loading Stash...
        </div>
      </StashChrome>
    );
  }

  if (!data) {
    return (
      <StashChrome data={null}>
        <div className="mx-auto max-w-md py-24 text-center">
          <h1 className="font-display text-[28px] font-bold text-foreground">Stash not found</h1>
          <p className="mt-2 text-[14px] leading-relaxed text-dim">
            {error || "This Stash is private, revoked, or unavailable to the current user."}
          </p>
        </div>
      </StashChrome>
    );
  }

  return (
    <StashChrome data={data}>
      <StashPageBody data={data} onRefresh={load} />
    </StashChrome>
  );
}

// Stable cover gradient per stash, mirroring the cover-1..6 utilities used
// elsewhere in the design. djb2-ish hash → bucket index so the same stash
// always gets the same cover.
function coverIndexFor(id: string): number {
  let h = 5381;
  for (let i = 0; i < id.length; i++) h = (h * 33 + id.charCodeAt(i)) >>> 0;
  return h % 6;
}

const COVER_GRADIENTS = [
  "linear-gradient(135deg, #FED7AA, #FCA5A5)",
  "linear-gradient(135deg, #DDD6FE, #BFDBFE)",
  "linear-gradient(135deg, #A7F3D0, #BAE6FD)",
  "linear-gradient(135deg, #FDE68A, #FECACA)",
  "linear-gradient(135deg, #C7D2FE, #FBCFE8)",
  "linear-gradient(135deg, #FECDD3, #FEF3C7)",
];

function StashPageBody({
  data,
  onRefresh,
}: {
  data: PublicStashDetail;
  onRefresh: () => Promise<void>;
}) {
  const { stash, workspace_name, items, can_write } = data;
  const groups = groupStashItems(items);
  const [addOpen, setAddOpen] = useState(false);

  const visibility: "public" | "private" | "workspace" = stash.access;
  const visClass = visibility === "public" ? "public" : visibility === "private" ? "private" : "";
  const cover = stash.cover_image_url
    ? { backgroundImage: `url(${stash.cover_image_url})` }
    : { backgroundImage: COVER_GRADIENTS[coverIndexFor(stash.id)] };

  return (
    <div className="scroll-thin min-h-screen bg-background">
      {/* Cover banner mirrors the workspace home identity strip. */}
      <div className="h-[72px] w-full bg-cover bg-center" style={cover} />

      <div className="mx-auto max-w-[920px] px-12 pb-20">
        {/* Identity strip: icon overlaps banner, title + meta + actions.
            Layout/spacing identical to workspace home's identity strip. */}
        <div className="flex items-start justify-between gap-3 pt-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="-mt-9 flex h-12 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-[10px] border-2 border-base bg-base text-[var(--color-brand-700)] shadow-sm">
              <StashHeaderGlyph />
            </span>
            <div className="min-w-0">
              <h1 className="m-0 flex min-w-0 items-center gap-2 truncate font-display text-[20px] font-bold leading-tight tracking-[-0.015em] text-foreground">
                <span className="truncate">{stash.title}</span>
                <span className={`stash-chip ${visClass}`.trim()}>
                  <span className="dot" />
                  {visibility}
                </span>
              </h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-muted">
                <span>
                  {items.length} item{items.length === 1 ? "" : "s"}
                </span>
                {stash.updated_at && (
                  <>
                    <span className="text-muted/60">·</span>
                    <span>updated {relativeTime(stash.updated_at)}</span>
                  </>
                )}
                {workspace_name && (
                  <>
                    <span className="text-muted/60">·</span>
                    <span className="truncate">in {workspace_name}</span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-shrink-0 items-center gap-1.5 pt-1">
            <ShareStashButton stash={stash} canWrite={can_write} onChanged={onRefresh} />
            {can_write ? (
              <button
                type="button"
                onClick={() => setAddOpen(true)}
                className="rounded-md bg-[var(--color-brand-600)] px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
              >
                + Add things
              </button>
            ) : (
              // Forking only makes sense when the viewer doesn't already have
              // write access to this stash in its own workspace.
              <AddToWorkspaceButton slug={stash.slug} sourceWorkspaceId={stash.workspace_id} />
            )}
          </div>
        </div>

        {/* About this Stash — read-only mirror of workspace home's editor. */}
        {stash.description && (
          <section className="mt-6">
            <div className="sys-label mb-1.5">About this Stash</div>
            <div className="rounded-[10px] border border-border bg-surface/40 px-[18px] py-[14px]">
              <p className="m-0 whitespace-pre-wrap text-[14.5px] leading-[1.7] text-foreground">
                {stash.description}
              </p>
            </div>
          </section>
        )}

        {/* Compact item lists by kind. Items deep-link to the editor /
            viewer in the owning workspace — no inline rendering. */}
        <div className="mt-6 flex flex-col gap-6">
          <StashItemSection
            title="Files"
            items={[...(groups.folder ?? []), ...(groups.page ?? []), ...(groups.file ?? [])]}
            workspaceId={stash.workspace_id}
          />
          <StashItemSection
            title="Sessions"
            items={groups.session ?? []}
            workspaceId={stash.workspace_id}
          />
          <StashItemSection
            title="Tables"
            items={groups.table ?? []}
            workspaceId={stash.workspace_id}
          />
          {items.length === 0 && (
            <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[13px] text-muted">
              No items yet.{" "}
              {can_write && (
                <button
                  type="button"
                  onClick={() => setAddOpen(true)}
                  className="font-medium text-[var(--color-brand-700)] hover:underline"
                >
                  Add things →
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {can_write && (
        <AddToStashModal
          open={addOpen}
          onClose={() => setAddOpen(false)}
          stashId={stash.id}
          workspaceId={stash.workspace_id}
          existingItems={items.map((it, i) => ({
            object_type: it.object_type,
            object_id: it.object_id,
            position: i,
            label_override: it.label,
          }))}
          onAdded={() => {
            void onRefresh();
          }}
        />
      )}
    </div>
  );
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} d ago`;
  return new Date(iso).toLocaleDateString();
}

// Single place to manage sharing: copy public URL, choose visibility,
// toggle discoverability. Anonymous viewers and non-writers only see the
// "Copy link" path.
function ShareStashButton({
  stash,
  canWrite,
  onChanged,
}: {
  stash: PublicStashDetail["stash"];
  canWrite: boolean;
  onChanged: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [vis, setVis] = useState(stash.access);
  const [discoverable, setDiscoverable] = useState(stash.discoverable);
  const [saving, setSaving] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (!open) return;
    function onDown(e: globalThis.MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(absoluteUrl(`/stashes/${stash.slug}`));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* ignore */
    }
  }

  async function applyChanges(next: Partial<{ access: typeof vis; discoverable: boolean }>) {
    setSaving(true);
    try {
      await updateStash(stash.id, next);
      await onChanged();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-base px-2.5 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
      >
        <ShareGlyph /> Share
      </button>
      {open && (
        <div
          ref={popoverRef}
          className="absolute right-0 top-full z-40 mt-1.5 w-[300px] rounded-lg border border-border bg-base p-3 shadow-lg"
        >
          <div className="sys-label mb-1">Public URL</div>
          <div className="flex gap-1.5">
            <input
              readOnly
              value={absoluteUrl(`/stashes/${stash.slug}`)}
              className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-[11.5px] font-mono text-foreground"
            />
            <button
              type="button"
              onClick={() => void copyLink()}
              className="rounded-md border border-border bg-base px-2 py-1.5 text-[11.5px] font-medium text-foreground hover:bg-raised"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>

          {canWrite && (
            <>
              <div className="sys-label mb-1 mt-3">Visibility</div>
              <div className="flex flex-col gap-1">
                <VisOption
                  label="Workspace"
                  hint="Anyone in the owning workspace can view"
                  value="workspace"
                  current={vis}
                  onChange={(v) => {
                    setVis(v);
                    void applyChanges({ access: v });
                  }}
                />
                <VisOption
                  label="Private"
                  hint="Only the owner and explicit members"
                  value="private"
                  current={vis}
                  onChange={(v) => {
                    setVis(v);
                    void applyChanges({ access: v });
                  }}
                />
                <VisOption
                  label="Public"
                  hint="Anyone with the URL can view"
                  value="public"
                  current={vis}
                  onChange={(v) => {
                    setVis(v);
                    void applyChanges({ access: v });
                  }}
                />
              </div>

              {vis === "public" && (
                <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-2 py-1.5">
                  <input
                    type="checkbox"
                    checked={discoverable}
                    onChange={(e) => {
                      setDiscoverable(e.target.checked);
                      void applyChanges({ discoverable: e.target.checked });
                    }}
                  />
                  <span className="text-[12px] text-foreground">
                    List on Discover
                  </span>
                </label>
              )}

              {saving && (
                <div className="mt-2 text-[11px] text-muted">Saving…</div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function VisOption({
  label,
  hint,
  value,
  current,
  onChange,
}: {
  label: string;
  hint: string;
  value: "workspace" | "private" | "public";
  current: "workspace" | "private" | "public";
  onChange: (next: "workspace" | "private" | "public") => void;
}) {
  const active = value === current;
  return (
    <button
      type="button"
      onClick={() => onChange(value)}
      className={
        "flex items-start gap-2 rounded-md px-2 py-1.5 text-left text-[12px] " +
        (active ? "bg-[var(--color-brand-50)]" : "hover:bg-raised")
      }
    >
      <span
        className={
          "mt-[3px] inline-block h-3 w-3 flex-shrink-0 rounded-full border-2 " +
          (active
            ? "border-[var(--color-brand-600)] bg-[var(--color-brand-500)]"
            : "border-border bg-base")
        }
      />
      <span className="min-w-0">
        <span className="block font-medium text-foreground">{label}</span>
        <span className="block text-[11px] text-muted">{hint}</span>
      </span>
    </button>
  );
}

function ShareGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <path d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98" />
    </svg>
  );
}

function absoluteUrl(path: string): string {
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}

function groupStashItems(items: PublicStashItem[]): StashItemGroup {
  const groups: StashItemGroup = {};
  for (const item of items) {
    groups[item.object_type] = [...(groups[item.object_type] ?? []), item];
  }
  return groups;
}

function StashHeaderGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 7h16l-1.3 11a2 2 0 0 1-2 1.8H7.3a2 2 0 0 1-2-1.8L4 7z" />
      <path d="M9 7V5a3 3 0 0 1 6 0v2" />
    </svg>
  );
}

// Compact item list — each item deep-links to its editor / viewer in the
// owning workspace. No inline content rendering; the user wanted the stash
// detail page to be a directory, not a wall of embedded documents.
function StashItemSection({
  title,
  items,
  workspaceId,
}: {
  title: string;
  items: PublicStashItem[];
  workspaceId: string;
}) {
  if (items.length === 0) return null;
  return (
    <section>
      <div className="mb-2 flex items-baseline gap-2 border-b border-border-subtle pb-1.5">
        <h2 className="m-0 font-display text-[15px] font-semibold text-foreground">{title}</h2>
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {items.length}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        {items.map((item) => (
          <StashItemRow key={`${item.object_type}-${item.object_id}`} item={item} workspaceId={workspaceId} />
        ))}
      </div>
    </section>
  );
}

function StashItemRow({ item, workspaceId }: { item: PublicStashItem; workspaceId: string }) {
  const href = hrefForItem(item, workspaceId);
  const sub = subtitleForItem(item);
  const tint = tintForKind(item.object_type);

  const content = (
    <>
      <span className={"flex h-5 w-5 flex-shrink-0 items-center justify-center " + tint}>
        <KindGlyph kind={item.object_type} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-medium text-foreground">
          {item.label || "(untitled)"}
        </span>
        {sub && (
          <span className="block truncate text-[11.5px] text-muted">{sub}</span>
        )}
      </span>
      {href && (
        <span className="hidden text-[11.5px] text-muted sm:inline">Open →</span>
      )}
    </>
  );

  const cls =
    "flex items-center gap-2.5 rounded-md px-2 py-1.5 " +
    (href ? "hover:bg-raised" : "opacity-60");

  return href ? (
    <Link href={href} className={cls}>
      {content}
    </Link>
  ) : (
    <div className={cls}>{content}</div>
  );
}

function hrefForItem(item: PublicStashItem, workspaceId: string): string | null {
  if (item.object_type === "page") return `/workspaces/${workspaceId}/p/${item.object_id}`;
  if (item.object_type === "folder")
    return `/workspaces/${workspaceId}/folders/${item.object_id}`;
  if (item.object_type === "file") return `/workspaces/${workspaceId}/f/${item.object_id}`;
  if (item.object_type === "session") {
    const sid =
      (item.inline?.session as { session_id?: string } | undefined)?.session_id ||
      item.object_id;
    return `/workspaces/${workspaceId}/sessions/${encodeURIComponent(sid)}`;
  }
  if (item.object_type === "table") return `/tables/${item.object_id}?workspaceId=${workspaceId}`;
  return null;
}

function subtitleForItem(item: PublicStashItem): string {
  if (item.object_type === "session") {
    const s = item.inline?.session as { agent_name?: string; events?: unknown[] } | undefined;
    if (s) return [s.agent_name, s.events?.length ? `${s.events.length} events` : null].filter(Boolean).join(" · ");
  }
  if (item.object_type === "file") {
    const f = item.inline as { content_type?: string; size_bytes?: number } | undefined;
    if (f?.content_type) return f.content_type;
  }
  if (item.object_type === "page") {
    const p = item.inline?.page as { content_type?: string } | undefined;
    return p?.content_type === "html" ? "html page" : "page";
  }
  return "";
}

function tintForKind(kind: PublicStashItem["object_type"]): string {
  if (kind === "session") return "text-[var(--color-agent)]";
  if (kind === "table") return "text-emerald-600";
  if (kind === "folder") return "text-muted";
  return "text-muted";
}

function KindGlyph({ kind }: { kind: PublicStashItem["object_type"] }) {
  if (kind === "folder")
    return (
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
      </svg>
    );
  if (kind === "page")
    return (
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
        <path d="M14 3v5h5" />
      </svg>
    );
  if (kind === "session")
    return (
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M21 12c0 4.4-4 8-9 8-1.4 0-2.8-.3-4-.8L3 21l1.5-4C3.6 15.7 3 13.9 3 12c0-4.4 4-8 9-8s9 3.6 9 8z" />
      </svg>
    );
  if (kind === "table")
    return (
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 10h18M3 16h18M9 4v16M15 4v16" />
      </svg>
    );
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

