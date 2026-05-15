"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import DownloadMenu, { downloadBlob } from "../../../../../components/DownloadMenu";
import { PageIcon } from "../../../../../components/StashIcons";
import HtmlPageView from "../../../../../components/workspace/HtmlPageView";
import MarkdownEditor, { type SaveStatus } from "../../../../../components/workspace/MarkdownEditor";
import { useAuth } from "../../../../../hooks/useAuth";
import {
  getFolderContents,
  getPage,
  listObjectStashes,
  updatePage,
  type FolderBreadcrumb,
  type WorkspaceStash,
} from "../../../../../lib/api";
import type { Page } from "../../../../../lib/types";

function wrapHtml(title: string, body: string): string {
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(
    title
  )}</title><style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2em auto;padding:0 1em;line-height:1.6;color:#1a1a1a}h1,h2,h3{line-height:1.25}pre{background:#f6f6f6;padding:1em;overflow:auto;border-radius:6px}code{background:#f6f6f6;padding:.1em .3em;border-radius:3px}</style></head><body>${body}</body></html>`;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" : c === '"' ? "&quot;" : "&#39;"
  );
}

export default function StashPageView() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const pageId = params.pageId as string;
  const { user, loading, logout } = useAuth();

  const [page, setPage] = useState<Page | null>(null);
  const [folderChain, setFolderChain] = useState<FolderBreadcrumb[]>([]);
  const [containingStashes, setContainingStashes] = useState<WorkspaceStash[]>([]);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [error, setError] = useState("");

  useBreadcrumbs(
    [
      ...folderChain.map((c) => ({
        label: c.name,
        href: `/workspaces/${workspaceId}/folders/${c.id}`,
      })),
      { label: page ? page.name.replace(/\.md$/, "") : "Page" },
    ],
    `${workspaceId}/page/${pageId}/${page?.name ?? ""}/${folderChain.map((c) => c.id).join(",")}`
  );

  const load = useCallback(async () => {
    try {
      const p = await getPage(workspaceId, pageId);
      setPage(p);
      setContainingStashes(await listObjectStashes(workspaceId, "page", pageId));
      if (p.folder_id) {
        const contents = await getFolderContents(workspaceId, p.folder_id);
        setFolderChain(contents.breadcrumbs);
      } else {
        setFolderChain([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load page");
    }
  }, [workspaceId, pageId]);

  const handleSave = useCallback(
    async (content: string) => {
      try {
        const updated = await updatePage(workspaceId, pageId, { content });
        setPage(updated);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Save failed");
      }
    },
    [workspaceId, pageId]
  );

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  const updatedAt = page?.updated_at
    ? new Date(page.updated_at).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="h-16 w-full bg-gradient-to-r from-[var(--color-brand-200)] via-[var(--color-brand-100)] to-amber-100" />
        <div className="mx-auto -mt-6 grid max-w-5xl gap-8 px-12 pb-20 lg:grid-cols-[minmax(0,1fr)_240px]">
          <main className="min-w-0">
          <div className="flex h-12 w-12 items-center justify-center text-5xl text-muted">
            <PageIcon />
          </div>
          <h1 className="mt-1 font-display text-[36px] font-bold tracking-tight text-foreground">
            {(page?.name || "").replace(/\.md$/, "")}
          </h1>
          <div className="mt-1 flex items-center justify-between gap-3 text-[12px] text-muted">
            <div className="flex items-center gap-3">
              {updatedAt && (
                <span>
                  Last edited {updatedAt}
                </span>
              )}
              {page && page.content_type !== "html" && (
                <span
                  className={
                    saveStatus === "saving"
                      ? "text-amber-500"
                      : saveStatus === "dirty"
                      ? "text-amber-600"
                      : "text-emerald-600"
                  }
                >
                  {saveStatus === "saving" ? "Saving…" : saveStatus === "dirty" ? "Unsaved" : "Saved"}
                </span>
              )}
            </div>
            {page && (
              <DownloadMenu
                options={[
                  {
                    label: "Markdown (.md)",
                    onSelect: () =>
                      downloadBlob(
                        page.content_markdown ?? "",
                        "text/markdown",
                        `${page.name.replace(/\.md$/, "")}.md`
                      ),
                  },
                  {
                    label: "HTML (.html)",
                    onSelect: () =>
                      downloadBlob(
                        wrapHtml(page.name, page.content_html ?? ""),
                        "text/html",
                        `${page.name.replace(/\.md$/, "")}.html`
                      ),
                  },
                  {
                    label: "PDF (print)",
                    onSelect: () => window.print(),
                  },
                ]}
              />
            )}
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          <article className="mt-8 text-[15px] leading-relaxed text-foreground">
            {page ? (
              page.content_type === "html" ? (
                <HtmlPageView
                  html={page.content_html || ""}
                  title={page.name}
                  layout={page.html_layout}
                />
              ) : (
                <MarkdownEditor
                  workspaceId={workspaceId}
                  file={page}
                  onSave={handleSave}
                  onSaveStatusChange={setSaveStatus}
                  onNavigateInternal={(href) => router.push(href)}
                />
              )
            ) : (
              <p className="text-muted">Loading…</p>
            )}
          </article>
          </main>
          <StashAside stashes={containingStashes} />
        </div>
      </div>
  );
}

function StashAside({ stashes }: { stashes: WorkspaceStash[] }) {
  return (
    <aside className="mt-20 hidden lg:block">
      <div className="sticky top-16 rounded-lg border border-border-subtle bg-surface p-3">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          In Stashes
        </div>
        {stashes.length > 0 ? (
          <div className="mt-2 flex flex-col gap-1.5">
            {stashes.map((stash) => (
              <a
                key={stash.id}
                href={`/stashes/${stash.slug}`}
                className="rounded-md border border-border-subtle bg-base px-2.5 py-2 text-[12px] text-foreground hover:border-brand hover:text-brand"
              >
                <span className="block truncate font-medium">{stash.title}</span>
                <span className="mt-0.5 block text-[11px] text-muted">
                  {stash.items.length} item{stash.items.length === 1 ? "" : "s"}
                </span>
              </a>
            ))}
          </div>
        ) : (
          <div className="mt-2 text-[12px] leading-relaxed text-muted">
            This page is not in a Stash yet.
          </div>
        )}
      </div>
    </aside>
  );
}
