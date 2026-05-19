"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import AppShell from "../../../../../../components/AppShell";
import { useBreadcrumbs } from "../../../../../../components/BreadcrumbContext";
import { StashItemSkeleton } from "../../../../../../components/SkeletonStates";
import HtmlPageView from "../../../../../../components/workspace/HtmlPageView";
import { useAuth } from "../../../../../../hooks/useAuth";
import {
  ApiError,
  getPublicStash,
  type PublicStashDetail,
  type PublicStashItem,
} from "../../../../../../lib/api";

// Stash-scoped item viewer.
//
// SECURITY MODEL: this page only ever reads through `getPublicStash(slug)`,
// which is gated server-side by stash readability:
//   - public stash → readable by anyone (signed in or not)
//   - workspace stash → readable by workspace members
//   - private stash → readable by explicit stash members only
// The endpoint returns ONLY the items inside that stash, with their content
// inlined. We do not call any workspace-scoped endpoint and we do not relax
// any existing permission check. Items only become reachable here when the
// stash owner has explicitly added them to a stash the viewer can read.

interface Props {
  slug: string;
  type: string;
  itemId: string;
}

function Chrome({
  data,
  item,
  children,
}: {
  data: PublicStashDetail | null;
  item: PublicStashItem | null;
  children: ReactNode;
}) {
  const { user, loading, logout } = useAuth();
  useBreadcrumbs(
    [
      { label: "Stashes", href: "/stashes" },
      {
        label: data?.stash.title ?? "Stash",
        href: data ? `/stashes/${data.stash.slug}` : "/stashes",
      },
      { label: item?.label || "Item" },
    ],
    `stash-item/${data?.stash.id ?? "loading"}/${item?.object_id ?? "loading"}`
  );
  if (loading) {
    return <StashItemSkeleton />;
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

export default function StashItemClient({ slug, type, itemId }: Props) {
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
        setError("Stash not found");
      } else {
        setError(e instanceof Error ? e.message : "Failed to load");
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
      <Chrome data={data} item={null}>
        <StashItemSkeleton />
      </Chrome>
    );
  }

  if (!data) {
    return (
      <Chrome data={null} item={null}>
        <NotFound title="Stash not found" body={error || "This Stash is unavailable."} />
      </Chrome>
    );
  }

  const item = data.items.find(
    (it) => it.object_type === type && it.object_id === itemId
  );

  if (!item) {
    return (
      <Chrome data={data} item={null}>
        <NotFound
          title="Item not in this Stash"
          body="This item isn't part of the Stash anymore, or never was."
          backHref={`/stashes/${slug}`}
        />
      </Chrome>
    );
  }

  return (
    <Chrome data={data} item={item}>
      <ItemPage stashSlug={slug} stashTitle={data.stash.title} item={item} />
    </Chrome>
  );
}

function NotFound({
  title,
  body,
  backHref,
}: {
  title: string;
  body: string;
  backHref?: string;
}) {
  return (
    <div className="mx-auto max-w-md py-24 text-center">
      <h1 className="font-display text-[24px] font-bold text-foreground">{title}</h1>
      <p className="mt-2 text-[14px] leading-relaxed text-dim">{body}</p>
      {backHref && (
        <Link
          href={backHref}
          className="mt-4 inline-block rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
        >
          ← Back to stash
        </Link>
      )}
    </div>
  );
}

function ItemPage({
  stashSlug,
  stashTitle,
  item,
}: {
  stashSlug: string;
  stashTitle: string;
  item: PublicStashItem;
}) {
  return (
    <div className="scroll-thin min-h-screen bg-background">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <Link
          href={`/stashes/${stashSlug}`}
          className="inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-foreground"
        >
          ← {stashTitle}
        </Link>
        <h1 className="mt-3 m-0 font-display text-[22px] font-bold leading-tight tracking-[-0.015em] text-foreground">
          {item.label || "(untitled)"}
        </h1>
        <div className="mt-1 text-[11.5px] uppercase tracking-wide text-muted">
          {item.object_type}
        </div>

        <div className="mt-6">
          <ItemBody item={item} />
        </div>
      </div>
    </div>
  );
}

function ItemBody({ item }: { item: PublicStashItem }) {
  if (Object.keys(item.inline).length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[13px] text-muted">
        This item is no longer available in the Stash.
      </p>
    );
  }
  if (item.object_type === "page") return <PageBody item={item} />;
  if (item.object_type === "table") return <TableBody item={item} />;
  if (item.object_type === "file") return <FileBody item={item} />;
  if (item.object_type === "folder") return <FolderBody item={item} />;
  if (item.object_type === "session") return <SessionBody item={item} />;
  return null;
}

function PageBody({ item }: { item: PublicStashItem }) {
  const p = (item.inline as {
    page?: {
      content_type?: string;
      content_markdown?: string;
      content_html?: string;
      html_layout?: "responsive" | "fixed-aspect";
      name?: string;
    };
  }).page;
  if (!p) return null;
  if (p.content_type === "html") {
    return (
      <HtmlPageView
        html={p.content_html || ""}
        title={p.name || item.label}
        layout={p.html_layout}
      />
    );
  }
  return (
    <div className="markdown-content">
      <Markdown remarkPlugins={[remarkGfm]}>{p.content_markdown || ""}</Markdown>
    </div>
  );
}

interface InlineTableColumn {
  id?: string;
  name: string;
  type?: string;
}

function TableBody({ item }: { item: PublicStashItem }) {
  const t = item.inline as {
    description?: string;
    columns?: InlineTableColumn[];
    rows?: { data: Record<string, unknown>; row_order?: number }[];
  };
  const columns = t.columns ?? [];
  const rows = t.rows ?? [];
  return (
    <div className="space-y-4">
      {t.description && (
        <p className="text-[13.5px] leading-relaxed text-foreground">{t.description}</p>
      )}
      <div className="scroll-thin overflow-x-auto rounded-lg border border-border bg-base">
        <table className="w-full border-collapse text-[13px]">
          <thead className="bg-surface text-[11px] uppercase tracking-wide text-muted">
            <tr>
              {columns.map((col) => (
                <th key={col.id ?? col.name} className="border-b border-border px-3 py-2 text-left font-medium">
                  {col.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-border-subtle last:border-0">
                {columns.map((col) => {
                  // Backend stores row.data keyed by column id (col_xxx).
                  // Fall back to column name for older rows.
                  const key = col.id ?? col.name;
                  const value = row.data?.[key] ?? row.data?.[col.name];
                  return (
                    <td key={key} className="px-3 py-2 align-top text-foreground">
                      {formatCell(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="px-3 py-6 text-center text-[12.5px] text-muted">No rows.</div>
        )}
      </div>
      <p className="text-[11.5px] text-muted">
        {rows.length} row{rows.length === 1 ? "" : "s"} · read-only view from this Stash
      </p>
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function FileBody({ item }: { item: PublicStashItem }) {
  const f = item.inline as {
    name?: string;
    content_type?: string;
    size_bytes?: number;
    url?: string;
    created_at?: string;
  };
  const isPdf = (f.content_type || "").includes("pdf");
  const isImage = (f.content_type || "").startsWith("image/");
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-base px-4 py-3 text-[13px]">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate font-medium text-foreground">{f.name}</div>
            <div className="mt-0.5 text-[11.5px] text-muted">
              {f.content_type || "file"} · {formatSize(f.size_bytes ?? 0)}
            </div>
          </div>
          {f.url && (
            <a
              href={f.url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-border bg-base px-2.5 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
            >
              Download ↗
            </a>
          )}
        </div>
      </div>
      {f.url && isPdf && (
        <iframe
          src={f.url}
          title={f.name || "PDF"}
          className="h-[80vh] w-full rounded-lg border border-border bg-base"
        />
      )}
      {f.url && isImage && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={f.url} alt={f.name || ""} className="max-w-full rounded-lg border border-border" />
      )}
    </div>
  );
}

function FolderBody({ item }: { item: PublicStashItem }) {
  const inline = item.inline as {
    pages?: {
      id: string;
      name: string;
      content_type?: string;
      content_markdown?: string;
      content_html?: string;
      html_layout?: "responsive" | "fixed-aspect";
    }[];
    files?: { id: string; name: string; content_type?: string; size_bytes?: number; url?: string }[];
  };
  const pages = inline.pages ?? [];
  const files = inline.files ?? [];
  if (pages.length === 0 && files.length === 0) {
    return <p className="text-[13px] text-muted">Folder is empty.</p>;
  }
  return (
    <div className="space-y-4">
      {pages.length > 0 && (
        <section>
          <h2 className="m-0 mb-2 font-display text-[14px] font-semibold text-foreground">
            Pages
          </h2>
          <div className="space-y-3">
            {pages.map((p) => (
              <div key={p.id} className="rounded-lg border border-border bg-base px-4 py-3">
                <h3 className="m-0 mb-2 font-display text-[14px] font-semibold text-foreground">
                  {p.name}
                </h3>
                {p.content_type === "html" ? (
                  <HtmlPageView
                    html={p.content_html || ""}
                    title={p.name}
                    layout={p.html_layout}
                  />
                ) : (
                  <div className="markdown-content">
                    <Markdown remarkPlugins={[remarkGfm]}>{p.content_markdown || ""}</Markdown>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
      {files.length > 0 && (
        <section>
          <h2 className="m-0 mb-2 font-display text-[14px] font-semibold text-foreground">
            Files
          </h2>
          <div className="space-y-1.5">
            {files.map((f) => (
              <a
                key={f.id}
                href={f.url}
                target="_blank"
                rel="noreferrer"
                className="block rounded-md border border-border-subtle bg-base px-3 py-2 text-[13px] text-foreground hover:bg-raised"
              >
                <span className="block truncate font-medium">{f.name}</span>
                <span className="mt-0.5 block text-[11.5px] text-muted">
                  {f.content_type} · {formatSize(f.size_bytes ?? 0)}
                </span>
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

interface InlineSessionEvent {
  agent_name?: string;
  event_type?: string;
  tool_name?: string | null;
  content?: string;
  created_at?: string;
}

function SessionBody({ item }: { item: PublicStashItem }) {
  const s = (item.inline as {
    session?: {
      summary?: string | null;
      agent_name?: string;
      started_at?: string | null;
      finished_at?: string | null;
      events?: InlineSessionEvent[];
    };
  }).session;
  if (!s) return null;
  const events = s.events ?? [];
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-base px-4 py-3 text-[13px] text-foreground">
        <div className="flex flex-wrap items-center gap-3 text-[11.5px] uppercase tracking-wide text-muted">
          {s.agent_name && <span>agent · {s.agent_name}</span>}
          {s.started_at && <span>started · {new Date(s.started_at).toLocaleString()}</span>}
          {s.finished_at && <span>ended · {new Date(s.finished_at).toLocaleString()}</span>}
        </div>
        {s.summary && (
          <p className="mt-2 whitespace-pre-wrap text-foreground">{s.summary}</p>
        )}
      </div>
      <div className="space-y-2">
        {events.map((event, i) => (
          <div
            key={`${event.created_at ?? "evt"}-${i}`}
            className="rounded-md border border-border-subtle bg-base/40 px-3 py-2 text-[12.5px]"
          >
            <div className="flex items-center gap-2 text-[10.5px] uppercase tracking-wide text-muted">
              <span>{event.event_type || "event"}</span>
              {event.tool_name && <span>· {event.tool_name}</span>}
              {event.created_at && (
                <span>· {new Date(event.created_at).toLocaleTimeString()}</span>
              )}
            </div>
            <pre className="mt-1.5 m-0 whitespace-pre-wrap font-sans text-[12.5px] leading-relaxed text-foreground">
              {event.content || ""}
            </pre>
          </div>
        ))}
        {events.length === 0 && (
          <p className="text-[12.5px] text-muted">No events recorded.</p>
        )}
      </div>
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
