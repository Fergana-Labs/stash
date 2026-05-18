"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import AppShell from "../../../components/AppShell";
import { useBreadcrumbs } from "../../../components/BreadcrumbContext";
import HtmlPageView from "../../../components/workspace/HtmlPageView";
import { useAuth } from "../../../hooks/useAuth";
import { ApiError, createSharedStashPage, getPublicStash, type PublicStashDetail, type PublicStashItem } from "../../../lib/api";
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
            <CopyStashLinkButton slug={stash.slug} />
            <AddToWorkspaceButton slug={stash.slug} sourceWorkspaceId={stash.workspace_id} />
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

        {can_write ? (
          <div className="mt-6">
            <SharedPageComposer stashId={stash.id} onCreated={onRefresh} />
          </div>
        ) : null}

        <div className="mt-2">
          <StashSection
            id="files"
            title="Files"
            items={[...(groups.folder ?? []), ...(groups.page ?? []), ...(groups.file ?? [])]}
          />
          <StashSection id="sessions" title="Sessions" items={groups.session ?? []} />
          <StashSection id="tables" title="Tables" items={groups.table ?? []} />
        </div>
      </div>
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

function CopyStashLinkButton({ slug }: { slug: string }) {
  const [status, setStatus] = useState<"idle" | "copied" | "error">("idle");

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(absoluteUrl(`/stashes/${slug}`));
      setStatus("copied");
      window.setTimeout(() => setStatus("idle"), 1600);
    } catch {
      setStatus("error");
      window.setTimeout(() => setStatus("idle"), 3000);
    }
  }

  return (
    <button
      type="button"
      onClick={() => void copyLink()}
      className="rounded-lg border border-border-subtle bg-base px-4 py-2 text-[14px] font-medium text-foreground transition hover:border-brand hover:text-brand"
    >
      {status === "copied" ? "Copied" : status === "error" ? "Copy failed" : "Share"}
    </button>
  );
}

function absoluteUrl(path: string): string {
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}

function SharedPageComposer({
  stashId,
  onCreated,
}: {
  stashId: string;
  onCreated: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const createPage = async () => {
    const name = title.trim();
    if (!name) {
      setError("Name is required");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await createSharedStashPage(stashId, { name, content });
      setTitle("");
      setContent("");
      setOpen(false);
      await onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add page");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="border-b border-border-subtle py-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-[18px] font-bold text-ink">Shared pages</h2>
          <p className="mt-1 text-[13px] text-dim">
            Add a page that lives in this Stash instead of the source workspace Files.
          </p>
        </div>
        <button
          onClick={() => setOpen((value) => !value)}
          className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)]"
        >
          + Add page
        </button>
      </div>

      {open ? (
        <div className="mt-4 rounded-lg border border-border-subtle bg-surface p-4">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Page name"
            className="w-full rounded-md border border-border bg-base px-3 py-2 text-[14px] text-foreground outline-none focus:border-brand"
          />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Write Markdown..."
            rows={7}
            className="mt-3 w-full resize-y rounded-md border border-border bg-base px-3 py-2 text-[14px] leading-relaxed text-foreground outline-none focus:border-brand"
          />
          {error ? (
            <div className="mt-3 rounded-md border border-red-300/40 bg-red-500/10 px-3 py-2 text-[12px] text-red-400">
              {error}
            </div>
          ) : null}
          <div className="mt-3 flex justify-end gap-2">
            <button
              onClick={() => setOpen(false)}
              className="rounded-md border border-border-subtle px-3 py-1.5 text-[13px] text-muted hover:text-foreground"
            >
              Cancel
            </button>
            <button
              onClick={createPage}
              disabled={submitting}
              className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
            >
              {submitting ? "Adding..." : "Add to Stash"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
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

function StashSection({
  id,
  title,
  items,
}: {
  id: string;
  title: string;
  items: PublicStashItem[];
}) {
  if (items.length === 0) return null;
  return (
    <section id={id} className="scroll-mt-8 py-8 last:border-b-0">
      <div className="mb-3 flex items-baseline gap-2.5 border-b border-border pb-2">
        <h2 className="m-0 font-display text-[22px] font-bold leading-tight tracking-[-0.01em] text-foreground">
          {title}
        </h2>
        <span className="sys-label">
          {items.length} item{items.length === 1 ? "" : "s"}
        </span>
      </div>
      <div className="space-y-7">
        {items.map((item) => (
          <Item key={`${item.object_type}-${item.object_id}`} item={item} />
        ))}
      </div>
    </section>
  );
}

function Item({ item }: { item: PublicStashItem }) {
  return (
    <section id={`item-${item.object_type}-${item.object_id}`} className="scroll-mt-12">
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded border border-border-subtle px-2 py-0.5 font-mono text-[10px] uppercase text-muted">
          {item.object_type}
        </span>
        <h2 className="font-display text-[20px] font-bold text-ink">{item.label}</h2>
      </div>
      <div className="rounded-lg border border-border-subtle bg-surface p-5">
        <ItemBody item={item} />
      </div>
    </section>
  );
}

function ItemBody({ item }: { item: PublicStashItem }) {
  if (Object.keys(item.inline).length === 0) {
    return <p className="text-[13px] italic text-muted">This item is no longer available.</p>;
  }

  if (item.object_type === "folder") {
    const inline = item.inline as {
      pages?: {
        id: string;
        name: string;
        content_type?: "markdown" | "html";
        content_markdown: string;
        content_html?: string;
        html_layout?: "responsive" | "fixed-aspect";
      }[];
      files?: {
        id: string;
        name: string;
        content_type?: string;
        size_bytes?: number;
        url?: string;
      }[];
    };
    return (
      <div>
        {(inline.pages ?? []).map((p) => (
          <div key={p.id} className="mb-6 last:mb-0">
            <h3 className="font-display text-[16px] font-bold text-ink">{p.name}</h3>
            {p.content_type === "html" ? (
              <div className="mt-2">
                <HtmlPageView html={p.content_html || ""} title={p.name} layout={p.html_layout} />
              </div>
            ) : (
              <div className="markdown-content mt-2">
                <Markdown remarkPlugins={[remarkGfm]}>{p.content_markdown || "(empty)"}</Markdown>
              </div>
            )}
          </div>
        ))}
        {(inline.files ?? []).length > 0 ? (
          <div className={(inline.pages ?? []).length > 0 ? "mt-6" : ""}>
            <h3 className="mb-2 font-display text-[16px] font-bold text-ink">Files</h3>
            <div className="flex flex-col gap-2">
              {(inline.files ?? []).map((file) => (
                <a
                  key={file.id}
                  href={file.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-md border border-border-subtle bg-base px-3 py-2 text-[13px] text-foreground hover:border-brand hover:text-brand"
                >
                  <span className="block truncate font-medium">{file.name}</span>
                  <span className="mt-0.5 block text-[12px] text-dim">
                    {file.content_type} · {formatSize(file.size_bytes ?? 0)}
                  </span>
                </a>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  if (item.object_type === "page") {
    const inline = item.inline as {
      page?: {
        id: string;
        name: string;
        content_type?: "markdown" | "html";
        content_markdown: string;
        content_html?: string;
        html_layout?: "responsive" | "fixed-aspect";
      };
    };
    const page = inline.page;
    if (!page) return <p className="text-[13px] italic text-muted">This page is no longer available.</p>;
    return page.content_type === "html" ? (
      <HtmlPageView html={page.content_html || ""} title={page.name} layout={page.html_layout} />
    ) : (
      <div className="markdown-content">
        <Markdown remarkPlugins={[remarkGfm]}>{page.content_markdown || "(empty)"}</Markdown>
      </div>
    );
  }

  if (item.object_type === "table") {
    const inline = item.inline as {
      description?: string;
      columns?: { name: string; type: string }[];
      rows?: { data: Record<string, unknown> }[];
    };
    const cols = inline.columns ?? [];
    const rows = inline.rows ?? [];
    return (
      <div>
        {inline.description ? <p className="mb-3 text-[14px] text-dim">{inline.description}</p> : null}
        <div className="overflow-x-auto">
          <table className="min-w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle">
                {cols.map((column) => (
                  <th
                    key={column.name}
                    className="px-2 py-1 text-left font-mono text-[10px] uppercase text-muted"
                  >
                    {column.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index} className="border-b border-border-subtle/50">
                  {cols.map((column) => (
                    <td key={column.name} className="px-2 py-1 text-foreground">
                      {String(row.data[column.name] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (item.object_type === "file") {
    const inline = item.inline as {
      name?: string;
      content_type?: string;
      size_bytes?: number;
      url?: string;
    };
    const body = (
      <>
        <span className="block text-[13px] font-medium text-foreground">
          {inline.name || item.label}
        </span>
        <span className="mt-0.5 block text-[12px] text-dim">
          {inline.content_type} · {formatSize(inline.size_bytes ?? 0)}
        </span>
      </>
    );
    if (inline.url) {
      return (
        <a
          href={inline.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block rounded-md border border-border-subtle bg-base px-3 py-2 hover:border-brand hover:text-brand"
        >
          {body}
        </a>
      );
    }
    return (
      <p className="text-[13px] text-dim">{body}</p>
    );
  }

  if (item.object_type === "session") {
    const inline = item.inline as {
      session?: {
        session_id: string;
        agent_name?: string;
        summary?: string | null;
        files_touched?: string[] | string;
        artifacts?: {
          id: string;
          file_path: string;
          size_bytes: number;
          url: string;
        }[];
        events?: {
          event_type: string;
          tool_name?: string | null;
          content: string;
          created_at: string;
        }[];
      };
    };
    const session = inline.session;
    if (!session) return <p className="text-[13px] italic text-muted">Session unavailable.</p>;
    const filesTouched = normalizeStringList(session.files_touched);
    return (
      <div className="space-y-4">
        <p className="font-mono text-[11px] uppercase text-muted">
          {session.agent_name || "Agent session"} · {session.session_id}
        </p>
        {session.summary ? (
          <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-foreground">
            {session.summary}
          </p>
        ) : null}
        {(filesTouched.length || session.artifacts?.length) ? (
          <div className="grid gap-3 md:grid-cols-2">
            {filesTouched.length ? (
              <div>
                <h4 className="mb-2 font-mono text-[10px] uppercase text-muted">Files touched</h4>
                <div className="flex flex-col gap-1.5">
                  {filesTouched.map((file) => (
                    <div
                      key={file}
                      className="rounded-md border border-border-subtle bg-base px-2 py-1.5 font-mono text-[11px] text-foreground"
                    >
                      {file}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {session.artifacts?.length ? (
              <div>
                <h4 className="mb-2 font-mono text-[10px] uppercase text-muted">Artifacts</h4>
                <div className="flex flex-col gap-1.5">
                  {session.artifacts.map((artifact) => (
                    <a
                      key={artifact.id}
                      href={artifact.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded-md border border-border-subtle bg-base px-2 py-1.5 text-[12px] text-foreground hover:border-brand hover:text-brand"
                    >
                      <span className="block truncate">{artifact.file_path}</span>
                      <span className="mt-0.5 block text-[11px] text-muted">
                        {formatSize(artifact.size_bytes)}
                      </span>
                    </a>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="space-y-3">
          {(session.events ?? []).map((event, index) => (
            <div
              key={`${event.created_at}-${index}`}
              className="rounded-md border border-border-subtle bg-base p-3"
            >
              <div className="mb-1 flex items-center gap-2 font-mono text-[10px] uppercase text-muted">
                <span>{event.event_type}</span>
                {event.tool_name ? <span>{event.tool_name}</span> : null}
              </div>
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
                {event.content}
              </p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

function normalizeStringList(value: string[] | string | undefined): string[] {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  const parsed = JSON.parse(value);
  return Array.isArray(parsed) ? parsed.map(String) : [];
}
