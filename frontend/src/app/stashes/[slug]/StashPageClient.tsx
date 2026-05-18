"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type ChangeEvent,
} from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Heading from "@tiptap/extension-heading";
import Bold from "@tiptap/extension-bold";
import Italic from "@tiptap/extension-italic";
import TiptapLink from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";

import AppShell from "../../../components/AppShell";
import { useBreadcrumbs } from "../../../components/BreadcrumbContext";
import AddToStashModal from "../../../components/stash/AddToStashModal";
import StashShareDialog from "../../../components/stash/StashShareDialog";
import StashQuickAdd from "../../../components/StashQuickAdd";
import AgentActivityTimeline from "../../../components/viz/AgentActivityTimeline";
import EmbeddingSpaceExplorer from "../../../components/viz/EmbeddingSpaceExplorer";
import { useAuth } from "../../../hooks/useAuth";
import {
  ApiError,
  getActivityTimeline,
  getEmbeddingProjection,
  getPublicStash,
  updateStash,
  uploadFile,
  type PublicStashDetail,
  type PublicStashItem,
} from "../../../lib/api";
import type { ActivityTimeline, EmbeddingProjection } from "../../../lib/types";
import AddToWorkspaceButton from "./AddToWorkspaceButton";

type StashItemGroup = Partial<Record<PublicStashItem["object_type"], PublicStashItem[]>>;

// Same autosave window as workspace home — slow enough to coalesce
// keystrokes, fast enough to feel near-realtime.
const AUTOSAVE_MS = 1500;

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
  const { stash, workspace_name, items, can_write, can_manage_access } = data;
  const groups = groupStashItems(items);
  const [addOpen, setAddOpen] = useState(false);
  const [timeline, setTimeline] = useState<ActivityTimeline | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);

  useEffect(() => {
    // Visualizations are workspace-scoped — they show the owning workspace's
    // activity so the stash detail page has the same "knowledge map" feel
    // as the workspace home.
    let cancelled = false;
    Promise.allSettled([
      getActivityTimeline(365, "day", stash.workspace_id),
      getEmbeddingProjection(500, undefined, stash.workspace_id),
    ]).then(([t, p]) => {
      if (cancelled) return;
      if (t.status === "fulfilled") setTimeline(t.value);
      if (p.status === "fulfilled") setProjection(p.value);
    });
    return () => {
      cancelled = true;
    };
  }, [stash.workspace_id]);

  const visibility: "public" | "private" | "workspace" = stash.access;
  const visClass = visibility === "public" ? "public" : visibility === "private" ? "private" : "";
  const cover = stash.cover_image_url
    ? { backgroundImage: `url(${stash.cover_image_url})` }
    : { backgroundImage: COVER_GRADIENTS[coverIndexFor(stash.id)] };

  const existingSpecs = items.map((it, i) => ({
    object_type: it.object_type,
    object_id: it.object_id,
    position: i,
    label_override: it.label,
  }));

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
            <StashIconUpload
              iconUrl={stash.icon_url}
              canWrite={can_write}
              workspaceId={stash.workspace_id}
              stashId={stash.id}
              onChanged={onRefresh}
            />
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
            <ShareStashButton
              stash={stash}
              workspaceName={workspace_name}
              canWrite={can_write}
              canManageAccess={can_manage_access}
              onChanged={onRefresh}
            />
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

        {/* Quick-add: paste URL, drop a file. Items land in the workspace
            and are auto-appended to this stash's items. */}
        {can_write && (
          <section className="mt-6">
            <div className="sys-label mb-1.5">Quick add — paste a URL, drop a file</div>
            <StashQuickAdd
              workspaceId={stash.workspace_id}
              stashId={stash.id}
              existingItems={existingSpecs}
              onAdded={() => {
                void onRefresh();
              }}
            />
          </section>
        )}

        {/* About this Stash — inline editable for writers, read-only for
            viewers. Mirrors the workspace home editor. */}
        <StashDescriptionEditor
          stashId={stash.id}
          description={stash.description}
          canEdit={can_write}
          onSaved={() => {
            void onRefresh();
          }}
        />

        {/* Compact item lists by kind. Items deep-link to the editor /
            viewer in the owning workspace — no inline rendering. */}
        <div className="mt-6 flex flex-col gap-6">
          <StashItemSection
            title="Files"
            items={[...(groups.folder ?? []), ...(groups.page ?? []), ...(groups.file ?? [])]}
            stashSlug={stash.slug}
          />
          <StashItemSection
            title="Sessions"
            items={groups.session ?? []}
            stashSlug={stash.slug}
          />
          <StashItemSection
            title="Tables"
            items={groups.table ?? []}
            stashSlug={stash.slug}
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

        {/* Visualizations: agent activity + 3D embedding view of the
            owning workspace — same shape as workspace home. */}
        <section className="mt-8">
          <div className="sys-label mb-1.5">Agent activity — past year</div>
          <div className="card-soft overflow-x-auto p-3">
            {timeline && timeline.agents.length > 0 ? (
              <AgentActivityTimeline data={timeline} />
            ) : (
              <div className="px-2 py-6 text-center text-[12.5px] text-muted">
                No agent sessions yet. Push a transcript via Quick add or the CLI to populate this view.
              </div>
            )}
          </div>
        </section>

        <section className="mt-6">
          <div className="sys-label mb-1.5">Embedding space — workspace knowledge map</div>
          <div className="card-soft p-3">
            {projection && projection.points.length > 0 ? (
              <EmbeddingSpaceExplorer data={projection} />
            ) : (
              <div className="px-2 py-6 text-center text-[12.5px] text-muted">
                No embeddings indexed yet. Pages, table rows, and session events get embedded as they&apos;re added.
              </div>
            )}
          </div>
        </section>
      </div>

      {can_write && (
        <AddToStashModal
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
      await updateStash(stashId, { cover_image_url: uploaded.url });
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
          {uploading ? "Uploading…" : hasCustomCover ? "Change banner" : "Add banner"}
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
function StashIconUpload({
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
      await updateStash(stashId, { icon_url: uploaded.url });
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
    <StashHeaderGlyph />
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

// Inline-editable About section. Renders nothing for viewers when the
// description is empty so the page stays uncluttered. Mirrors the
// workspace home editor: TipTap + autosave-on-idle + click-to-focus
// affordance with dashed border that goes solid on focus.
function StashDescriptionEditor({
  stashId,
  description,
  canEdit,
  onSaved,
}: {
  stashId: string;
  description: string;
  canEdit: boolean;
  onSaved: () => void;
}) {
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef<string>(description);

  useEffect(() => {
    lastSaved.current = description;
  }, [description]);

  const editor = useEditor({
    immediatelyRender: false,
    editable: canEdit,
    content: description || "<p></p>",
    extensions: [
      StarterKit.configure({
        blockquote: false,
        codeBlock: false,
        heading: false,
        bold: false,
        italic: false,
        link: false,
        underline: false,
      }),
      Heading.configure({ levels: [1, 2, 3] }),
      Bold,
      Italic,
      TiptapLink.configure({ openOnClick: true, autolink: true }),
      Placeholder.configure({ placeholder: "Describe this Stash…" }),
    ],
    editorProps: {
      attributes: {
        class: "min-h-[120px] focus:outline-none file-page-body",
      },
    },
    onUpdate: ({ editor: ed }) => {
      const html = ed.getHTML();
      if (html === lastSaved.current) return;
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        lastSaved.current = html;
        await updateStash(stashId, { description: html });
        onSaved();
      }, AUTOSAVE_MS);
    },
  });

  useEffect(() => {
    if (!editor) return;
    if (editor.getHTML() === description) return;
    editor.commands.setContent(description || "<p></p>", { emitUpdate: false });
    lastSaved.current = description;
  }, [description, editor]);

  // useEditor() captures `editable` at creation time. When permission
  // info loads after first paint, toggle it on the live editor.
  useEffect(() => {
    if (!editor) return;
    editor.setEditable(canEdit);
  }, [editor, canEdit]);

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  if (!canEdit && !description) return null;

  return (
    <section className="mt-6">
      <div className="sys-label mb-1.5">About this Stash</div>
      <div
        onClick={() => editor?.commands.focus()}
        className={
          "rounded-[10px] border transition-colors " +
          (canEdit
            ? "border-dashed border-border bg-surface/40 px-[18px] py-[14px] cursor-text hover:border-[var(--color-brand-300)] hover:bg-[var(--color-brand-50)]/40 focus-within:border-[var(--color-brand-400)] focus-within:bg-base"
            : "border-border bg-surface/40 px-[18px] py-[14px]")
        }
      >
        <EditorContent editor={editor} />
      </div>
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

// Opens the Stash-level share sheet. Workspace invitations live in the
// workspace member modal instead.
function ShareStashButton({
  stash,
  workspaceName,
  canWrite,
  canManageAccess,
  onChanged,
}: {
  stash: PublicStashDetail["stash"];
  workspaceName: string;
  canWrite: boolean;
  canManageAccess: boolean;
  onChanged: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-base px-2.5 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
      >
        <ShareGlyph /> Share
      </button>
      <StashShareDialog
        stash={stash}
        workspaceName={workspaceName}
        canWrite={canWrite}
        canManageAccess={canManageAccess}
        open={open}
        onClose={() => setOpen(false)}
        onChanged={onChanged}
      />
    </>
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
  stashSlug,
}: {
  title: string;
  items: PublicStashItem[];
  stashSlug: string;
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
          <StashItemRow key={`${item.object_type}-${item.object_id}`} item={item} stashSlug={stashSlug} />
        ))}
      </div>
    </section>
  );
}

function StashItemRow({ item, stashSlug }: { item: PublicStashItem; stashSlug: string }) {
  const href = hrefForItem(item, stashSlug);
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

// Stash-scoped item URLs. Every link goes through /stashes/{slug}/items
// so the backend's stash readability check is the single gate. Items in a
// public stash become reachable to anyone with the link; items in a
// private or workspace stash stay gated to the people who can read that
// stash — regardless of whether the viewer is in the owning workspace.
function hrefForItem(item: PublicStashItem, stashSlug: string): string | null {
  if (
    item.object_type === "page" ||
    item.object_type === "folder" ||
    item.object_type === "file" ||
    item.object_type === "session" ||
    item.object_type === "table"
  ) {
    return `/stashes/${stashSlug}/items/${item.object_type}/${item.object_id}`;
  }
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
