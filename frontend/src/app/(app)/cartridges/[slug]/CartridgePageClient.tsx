"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";

import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import DescriptionEditor, {
  isBlankDescription,
} from "../../../../components/DescriptionEditor";
import {
  useActiveWorkspaceId,
  useShareAction,
} from "../../../../components/ShellChromeContext";
import { PublicCartridgeSkeleton, SkeletonBlock } from "../../../../components/SkeletonStates";
import AddToCartridgeModal from "../../../../components/cartridge/AddToCartridgeModal";
import CartridgeShareButton from "../../../../components/cartridge/CartridgeShareButton";
import { SettingsIcon, StashIcon } from "../../../../components/StashIcons";
import ContributorActivityTimeline from "../../../../components/viz/ContributorActivityTimeline";
import EmbeddingSpaceExplorer from "../../../../components/viz/EmbeddingSpaceExplorer";
import {
  ApiError,
  getActivityTimeline,
  getEmbeddingProjection,
  getPublicCartridge,
  getToken,
  updateCartridge,
  uploadFile,
  type PublicCartridgeDetail,
  type PublicCartridgeItem,
} from "../../../../lib/api";
import type { ActivityTimeline, EmbeddingProjection } from "../../../../lib/types";
import AddToWorkspaceButton from "./AddToWorkspaceButton";
import FileContentRenderer from "../../../../components/workspace/FileContentRenderer";
import { PageBody, SessionBody } from "./CartridgeItemBodies";

type CartridgeItemGroup = Partial<
  Record<PublicCartridgeItem["object_type"], PublicCartridgeItem[]>
>;

type InlineFile = {
  name?: string;
  content_type?: string;
  size_bytes?: number;
  url?: string;
  created_at?: string;
};

export default function CartridgePageClient({ slug }: { slug: string }) {
  const [data, setData] = useState<PublicCartridgeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getPublicCartridge(slug));
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

  useBreadcrumbs(
    [
      { label: "Cartridges", href: "/cartridges" },
      { label: data?.cartridge.title ?? "Stash" },
    ],
    `stash/${data?.cartridge.id ?? "loading"}`,
  );
  useActiveWorkspaceId(data?.cartridge.workspace_id ?? null);

  // Memo so the registered ReactNode is stable across renders — otherwise the
  // shell-chrome context would loop (AppShell re-renders → CartridgePageClient
  // re-renders → new node identity → setShareAction → AppShell re-renders).
  const stash = data?.cartridge ?? null;
  const canWrite = data?.can_write ?? false;
  const shareAction = useMemo(
    () =>
      stash ? (
        <CartridgeShareButton stash={stash} canWrite={canWrite} onChanged={load} />
      ) : null,
    [stash, canWrite, load],
  );
  useShareAction(shareAction);

  if (loading) {
    return <PublicCartridgeSkeleton />;
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="font-display text-[28px] font-bold text-foreground">
          Stash not found
        </h1>
        <p className="mt-2 text-[14px] leading-relaxed text-dim">
          {error ||
            "This cartridge is private, revoked, or unavailable to the current user."}
        </p>
      </div>
    );
  }

  return <CartridgePageBody data={data} onRefresh={load} />;
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
  "linear-gradient(135deg, #BFDBFE, #A7F3D0)",
  "linear-gradient(135deg, #A7F3D0, #BAE6FD)",
  "linear-gradient(135deg, #FDE68A, #FECACA)",
  "linear-gradient(135deg, #BAE6FD, #FED7AA)",
  "linear-gradient(135deg, #FECDD3, #FEF3C7)",
];

function CartridgePageBody({
  data,
  onRefresh,
}: {
  data: PublicCartridgeDetail;
  onRefresh: () => Promise<void>;
}) {
  const { cartridge: stash, workspace_name, items, can_write } = data;
  const groups = groupCartridgeItems(items);
  const primary = primaryItemForCartridge(data);
  const displayedItemCount = primary ? 1 : items.length;
  const [addOpen, setAddOpen] = useState(false);
  const [timeline, setTimeline] = useState<ActivityTimeline | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(
    null,
  );
  const [insightsLoaded, setInsightsLoaded] = useState(false);

  useEffect(() => {
    if (primary) {
      setTimeline(null);
      setProjection(null);
      setInsightsLoaded(true);
      return;
    }

    // Insight panels are workspace-member only — both endpoints require
    // auth. Anonymous public-stash viewers should skip the fetch entirely
    // (the panels render their empty-state without it).
    if (!getToken()) {
      setTimeline(null);
      setProjection(null);
      setInsightsLoaded(true);
      return;
    }

    // Visualizations are scoped to this cartridge's items — the sessions and
    // pages bundled into the Stash, not the owning workspace's full activity.
    let cancelled = false;
    setInsightsLoaded(false);
    Promise.allSettled([
      getActivityTimeline(30, "day", undefined, stash.id),
      getEmbeddingProjection(500, undefined, undefined, stash.id),
    ]).then(([t, p]) => {
      if (cancelled) return;
      if (t.status === "fulfilled") setTimeline(t.value);
      if (p.status === "fulfilled") setProjection(p.value);
      setInsightsLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, [primary, stash.id]);

  const cover = stash.cover_image_url
    ? { backgroundImage: `url(${stash.cover_image_url})` }
    : { backgroundImage: COVER_GRADIENTS[coverIndexFor(stash.id)] };

  const existingSpecs = items.map((it, i) => ({
    object_type: it.object_type,
    object_id: it.object_id,
    position: i,
    label_override: it.label,
  }));
  const author = stash.owner_display_name || stash.owner_name;

  return (
    <div className="scroll-thin min-h-screen bg-background">
      {/* Cover banner — click to upload (when can_write). Mirrors the
          workspace home identity strip but with edit affordance. */}
      <BannerImage
        cover={cover}
        canWrite={can_write}
        workspaceId={stash.workspace_id}
        stashId={stash.id}
        hasCustomCover={!!stash.cover_image_url}
        onChanged={onRefresh}
      />

      <div className="mx-auto max-w-[920px] px-12 pb-20">
        {/* Identity strip: icon overlaps banner, title + meta + actions. */}
        <div className="flex items-start justify-between gap-3 pt-4">
          <div className="flex min-w-0 items-center gap-3">
            <CartridgeIconUpload
              iconUrl={stash.icon_url}
              canWrite={can_write}
              workspaceId={stash.workspace_id}
              stashId={stash.id}
              onChanged={onRefresh}
            />
            <div className="min-w-0">
              <h1 className="m-0 truncate font-display text-[20px] font-bold leading-tight tracking-[-0.015em] text-foreground">
                {stash.title}
              </h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-muted">
                <span>by {author}</span>
                <span className="text-muted/60">·</span>
                <span>
                  {displayedItemCount} item
                  {displayedItemCount === 1 ? "" : "s"}
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
            {can_write ? (
              <>
                <Link
                  href={`/cartridges/${stash.slug}/settings`}
                  title="Stash settings"
                  aria-label="Stash settings"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-raised hover:text-foreground"
                >
                  <SettingsIcon />
                </Link>
                <button
                  type="button"
                  onClick={() => setAddOpen(true)}
                  className="rounded-md bg-[var(--color-brand-600)] px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
                >
                  + Add things
                </button>
              </>
            ) : (
              // Forking only makes sense when the viewer doesn't already have
              // write access to this cartridge in its own workspace.
              <AddToWorkspaceButton
                slug={stash.slug}
                sourceWorkspaceId={stash.workspace_id}
              />
            )}
          </div>
        </div>

        <CartridgeDescriptionEditor
          stashId={stash.id}
          workspaceId={stash.workspace_id}
          description={stash.description}
          canEdit={can_write}
          onSaved={() => {
            void onRefresh();
          }}
        />

        {primary ? (
          <>
            <PrimaryItemOpenLink
              kind={primary.kind}
              item={primary.item}
              workspaceId={stash.workspace_id}
              stashSlug={stash.slug}
            />
            {primary.kind === "file" ? (
              <SingleFilePreview item={primary.item} />
            ) : primary.kind === "page" ? (
              <section className="mt-6">
                <PageBody item={primary.item} />
              </section>
            ) : (
              <section className="mt-6">
                <SessionBody item={primary.item} />
              </section>
            )}
          </>
        ) : (
          <>
            {/* Compact item lists by kind. Items deep-link to the editor /
                viewer in the owning workspace — no inline rendering. */}
            <div className="mt-6 flex flex-col gap-6">
              {/* Two high-level taxonomies: Files (folders + pages + files +
                  tables — anything you could drop into Drive) and Sessions
                  (agent transcripts). Tables are a structured kind of file,
                  so they live under Files rather than as a separate section. */}
              <CartridgeItemSection
                title="Files"
                items={[
                  ...(groups.folder ?? []),
                  ...(groups.page ?? []),
                  ...(groups.file ?? []),
                  ...(groups.table ?? []),
                ]}
                stashSlug={stash.slug}
                workspaceId={stash.workspace_id}
              />
              <CartridgeItemSection
                title="Sessions"
                items={groups.session ?? []}
                stashSlug={stash.slug}
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

            {/* Visualizations: human/agent session activity + 3D embedding
                view scoped to this cartridge's items. Both panels are
                workspace-member features — hide them from anonymous
                public-stash viewers entirely so they don't see empty
                "no data" placeholders for tools they can't use. */}
            {getToken() && (
              <>
            <section className="mt-8">
              <div className="sys-label mb-1.5">
                Activity in this cartridge — last 30 days
              </div>
              <div className="card-soft overflow-x-auto p-3">
                {!insightsLoaded ? (
                  <SkeletonBlock className="h-40 w-full" />
                ) : timeline && timeline.contributors.length > 0 ? (
                  <ContributorActivityTimeline data={timeline} />
                ) : (
                  <div className="px-2 py-6 text-center text-[12.5px] text-muted">
                    No session activity in this cartridge yet. Add a session to
                    surface its agent commits here.
                  </div>
                )}
              </div>
            </section>

            <section className="mt-6">
              <div className="sys-label mb-1.5">
                Embedding map for this cartridge
              </div>
              <div className="card-soft p-3">
                {!insightsLoaded ? (
                  <SkeletonBlock className="h-40 w-full" />
                ) : projection && projection.points.length > 0 ? (
                  <EmbeddingSpaceExplorer data={projection} />
                ) : (
                  <div className="px-2 py-6 text-center text-[12.5px] text-muted">
                    No embeddings in this cartridge yet. Pages, table rows, and
                    session events get embedded as they&apos;re added.
                  </div>
                )}
              </div>
            </section>
              </>
            )}
          </>
        )}
      </div>

      {can_write && (
        <AddToCartridgeModal
          open={addOpen}
          onClose={() => setAddOpen(false)}
          stashId={stash.id}
          workspaceId={stash.workspace_id}
          existingItems={existingSpecs}
          onAdded={() => {
            void onRefresh();
          }}
        />
      )}
    </div>
  );
}

type PrimaryItem =
  | { kind: "file"; item: PublicCartridgeItem }
  | { kind: "page"; item: PublicCartridgeItem }
  | { kind: "session"; item: PublicCartridgeItem };

// "Single-content" cartridges — exactly one file, one page, or one session in
// the stash, nothing else — open straight to the artifact instead of the
// bundle chrome + viz section.
//
// Folders are intentionally NOT treated as incidental packaging. A folder
// is an open container the user may keep adding to; promising "this cartridge
// IS the page inside that folder" only stays true until the next upload.
function primaryItemForCartridge(data: PublicCartridgeDetail): PrimaryItem | null {
  if (data.items.length !== 1) return null;
  const only = data.items[0];
  if (only.object_type === "file") return { kind: "file", item: only };
  if (only.object_type === "page") return { kind: "page", item: only };
  if (only.object_type === "session") return { kind: "session", item: only };
  return null;
}

// Single-content cartridges render the artifact inline (read-only). The
// "Open in workspace" link is the escape hatch into the native viewer
// where edit affordances live for workspace members.
function PrimaryItemOpenLink({
  kind,
  item,
  workspaceId,
  stashSlug,
}: {
  kind: "file" | "page" | "session";
  item: PublicCartridgeItem;
  workspaceId: string;
  stashSlug: string;
}) {
  let href: string | null = null;
  if (kind === "file") {
    href = `/workspaces/${workspaceId}/f/${item.object_id}?stash=${encodeURIComponent(stashSlug)}`;
  } else if (kind === "page") {
    href = `/workspaces/${workspaceId}/p/${item.object_id}?stash=${encodeURIComponent(stashSlug)}`;
  } else {
    const session = (item.inline as { session?: { session_id?: string } }).session;
    if (session?.session_id) {
      href = `/workspaces/${workspaceId}/sessions/${encodeURIComponent(session.session_id)}?stash=${encodeURIComponent(stashSlug)}`;
    }
  }
  if (!href) return null;
  return (
    <div className="mt-4 flex justify-end">
      <Link
        href={href}
        className="inline-flex items-center gap-1 rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
      >
        Open in workspace ↗
      </Link>
    </div>
  );
}

function SingleFilePreview({ item }: { item: PublicCartridgeItem }) {
  const file = item.inline as InlineFile;
  const name = file.name || item.label || "Uploaded file";
  const contentType = file.content_type || "file";
  const size = formatFileSize(file.size_bytes ?? 0);

  return (
    <section className="mt-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="m-0 truncate font-display text-[16px] font-semibold text-foreground">
            {name}
          </h2>
          <div className="mt-0.5 text-[12px] text-muted">
            {contentType} · {size}
          </div>
        </div>
        {file.url && (
          <a
            href={file.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
          >
            Download ↗
          </a>
        )}
      </div>

      {!file.url ? (
        <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[13px] text-muted">
          This file is no longer available.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-surface">
          <FileContentRenderer
            url={file.url}
            name={name}
            contentType={contentType}
          />
        </div>
      )}
    </section>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// Clickable banner. Writers see a faint "Change banner" hint on hover and
// can upload a new image via the hidden file input. Uploads go through
// the workspace's file upload path; the resulting URL is saved on the
// stash record.
function BannerImage({
  cover,
  canWrite,
  workspaceId,
  stashId,
  hasCustomCover,
  onChanged,
}: {
  cover: { backgroundImage: string };
  canWrite: boolean;
  workspaceId: string;
  stashId: string;
  hasCustomCover: boolean;
  onChanged: () => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (inputRef.current) inputRef.current.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const uploaded = await uploadFile(workspaceId, file);
      await updateCartridge(stashId, { cover_image_url: uploaded.url });
      await onChanged();
    } finally {
      setUploading(false);
    }
  }

  if (!canWrite) {
    return <div className="h-[72px] w-full bg-cover bg-center" style={cover} />;
  }

  return (
    <div
      className="group relative h-[72px] w-full cursor-pointer bg-cover bg-center"
      style={cover}
      onClick={() => inputRef.current?.click()}
      title="Change banner"
    >
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/25 group-hover:opacity-100">
        <span className="rounded-md bg-black/60 px-2 py-1 text-[11.5px] font-medium text-white">
          {uploading
            ? "Uploading…"
            : hasCustomCover
              ? "Change banner"
              : "Add banner"}
        </span>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleChange}
      />
    </div>
  );
}

// Icon (logo) shown overlapping the banner. Writers can click to upload.
function CartridgeIconUpload({
  iconUrl,
  canWrite,
  workspaceId,
  stashId,
  onChanged,
}: {
  iconUrl: string | null;
  canWrite: boolean;
  workspaceId: string;
  stashId: string;
  onChanged: () => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (inputRef.current) inputRef.current.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const uploaded = await uploadFile(workspaceId, file);
      await updateCartridge(stashId, { icon_url: uploaded.url });
      await onChanged();
    } finally {
      setUploading(false);
    }
  }

  const base =
    "-mt-9 flex h-12 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-[10px] border-2 border-base bg-base text-[var(--color-brand-700)] shadow-sm";

  const inner = iconUrl ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={iconUrl} alt="" className="h-full w-full object-cover" />
  ) : (
    <StashIcon className="text-[24px]" />
  );

  if (!canWrite) {
    return <span className={base}>{inner}</span>;
  }

  return (
    <button
      type="button"
      onClick={() => inputRef.current?.click()}
      title="Change logo"
      className={
        base +
        " group relative cursor-pointer p-0 hover:ring-2 hover:ring-[var(--color-brand-300)]"
      }
    >
      {inner}
      <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/0 text-[10px] font-medium text-white opacity-0 transition group-hover:bg-black/40 group-hover:opacity-100">
        {uploading ? "…" : "Change"}
      </span>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleChange}
      />
    </button>
  );
}

function CartridgeDescriptionEditor({
  stashId,
  workspaceId,
  description,
  canEdit,
  onSaved,
}: {
  stashId: string;
  workspaceId: string;
  description: string;
  canEdit: boolean;
  onSaved: () => void;
}) {
  if (!canEdit && isBlankDescription(description)) return null;

  return (
    <section className="mt-5">
      <DescriptionEditor
        value={description}
        canEdit={canEdit}
        placeholder="Describe this cartridge…"
        ariaLabel="Stash description"
        workspaceId={workspaceId}
        onSave={async (html) => {
          await updateCartridge(stashId, { description: html });
          onSaved();
        }}
      />
    </section>
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

function groupCartridgeItems(items: PublicCartridgeItem[]): CartridgeItemGroup {
  const groups: CartridgeItemGroup = {};
  for (const item of items) {
    groups[item.object_type] = [...(groups[item.object_type] ?? []), item];
  }
  return groups;
}

// Compact item list — each item deep-links to its editor / viewer in the
// owning workspace. No inline content rendering; the user wanted the stash
// detail page to be a directory, not a wall of embedded documents.
function CartridgeItemSection({
  title,
  items,
  stashSlug,
  workspaceId,
}: {
  title: string;
  items: PublicCartridgeItem[];
  stashSlug: string;
  workspaceId: string;
}) {
  if (items.length === 0) return null;
  return (
    <section>
      <div className="mb-2 flex items-baseline gap-2 border-b border-border-subtle pb-1.5">
        <h2 className="m-0 font-display text-[15px] font-semibold text-foreground">
          {title}
        </h2>
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {items.length}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        {items.map((item) => (
          <CartridgeItemRow
            key={`${item.object_type}-${item.object_id}`}
            item={item}
            stashSlug={stashSlug}
            workspaceId={workspaceId}
          />
        ))}
      </div>
    </section>
  );
}

function CartridgeItemRow({
  item,
  stashSlug,
  workspaceId,
}: {
  item: PublicCartridgeItem;
  stashSlug: string;
  workspaceId: string;
}) {
  const href = hrefForItem(item, stashSlug, workspaceId);
  const sub = subtitleForItem(item);
  const tint = tintForKind(item.object_type);

  const content = (
    <>
      <span
        className={
          "flex h-5 w-5 flex-shrink-0 items-center justify-center " + tint
        }
      >
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
        <span className="hidden text-[11.5px] text-muted sm:inline">
          Open →
        </span>
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

// Stash item URLs are workspace-native routes. The `?stash=<slug>` query
// param is a backref hint: the viewer tries the workspace endpoint first
// (full permissions), and falls back to reading through the public stash
// payload when the user isn't a workspace member.
function hrefForItem(
  item: PublicCartridgeItem,
  stashSlug: string,
  workspaceId: string,
): string | null {
  const stash = encodeURIComponent(stashSlug);
  if (item.object_type === "file") {
    return `/workspaces/${workspaceId}/f/${item.object_id}?stash=${stash}`;
  }
  if (item.object_type === "page") {
    return `/workspaces/${workspaceId}/p/${item.object_id}?stash=${stash}`;
  }
  if (item.object_type === "folder") {
    return `/workspaces/${workspaceId}/folders/${item.object_id}?stash=${stash}`;
  }
  if (item.object_type === "session") {
    // Session URLs are keyed on the human-readable session_id, not the
    // row UUID. The string lives in inline.session.session_id.
    const sessionRow = (item.inline as { session?: { session_id?: string } }).session;
    if (!sessionRow?.session_id) return null;
    return `/workspaces/${workspaceId}/sessions/${encodeURIComponent(sessionRow.session_id)}?stash=${stash}`;
  }
  if (item.object_type === "table") {
    return `/tables/${item.object_id}?stash=${stash}`;
  }
  return null;
}

function subtitleForItem(item: PublicCartridgeItem): string {
  if (item.object_type === "session") {
    const s = item.inline?.session as
      | { agent_name?: string; events?: unknown[] }
      | undefined;
    if (s)
      return [
        s.agent_name,
        s.events?.length ? `${s.events.length} events` : null,
      ]
        .filter(Boolean)
        .join(" · ");
  }
  if (item.object_type === "file") {
    const f = item.inline as
      | { content_type?: string; size_bytes?: number }
      | undefined;
    if (f?.content_type) return f.content_type;
  }
  if (item.object_type === "page") {
    const p = item.inline?.page as { content_type?: string } | undefined;
    return p?.content_type === "html" ? "html page" : "page";
  }
  return "";
}

function tintForKind(kind: PublicCartridgeItem["object_type"]): string {
  if (kind === "session") return "text-[var(--color-agent)]";
  if (kind === "table") return "text-emerald-600";
  if (kind === "folder") return "text-muted";
  return "text-muted";
}

function KindGlyph({ kind }: { kind: PublicCartridgeItem["object_type"] }) {
  if (kind === "folder")
    return (
      <svg
        viewBox="0 0 24 24"
        width="14"
        height="14"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
      </svg>
    );
  if (kind === "page")
    return (
      <svg
        viewBox="0 0 24 24"
        width="14"
        height="14"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
        <path d="M14 3v5h5" />
      </svg>
    );
  if (kind === "session")
    return (
      <svg
        viewBox="0 0 24 24"
        width="14"
        height="14"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <path d="M21 12c0 4.4-4 8-9 8-1.4 0-2.8-.3-4-.8L3 21l1.5-4C3.6 15.7 3 13.9 3 12c0-4.4 4-8 9-8s9 3.6 9 8z" />
      </svg>
    );
  if (kind === "table")
    return (
      <svg
        viewBox="0 0 24 24"
        width="14"
        height="14"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 10h18M3 16h18M9 4v16M15 4v16" />
      </svg>
    );
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
    >
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}
