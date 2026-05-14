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
  getWorkspace,
  listWorkspacePages,
  updatePage,
  type FolderBreadcrumb,
  type WorkspacePageEntry,
} from "../../../../../lib/api";
import type { Page, Workspace } from "../../../../../lib/types";

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
  const stashId = params.stashId as string;
  const pageId = params.pageId as string;
  const { user, loading, logout } = useAuth();

  const [stash, setStash] = useState<Workspace | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [folderChain, setFolderChain] = useState<FolderBreadcrumb[]>([]);
  const [pageIndex, setPageIndex] = useState<WorkspacePageEntry[]>([]);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [error, setError] = useState("");

  useBreadcrumbs(
    [
      ...folderChain.map((c) => ({
        label: c.name,
        href: `/stashes/${stashId}/folders/${c.id}`,
      })),
      { label: page ? page.name.replace(/\.md$/, "") : "Page" },
    ],
    `${stashId}/page/${pageId}/${page?.name ?? ""}/${folderChain.map((c) => c.id).join(",")}`
  );

  const load = useCallback(async () => {
    try {
      const [workspace, p, index] = await Promise.all([
        getWorkspace(stashId),
        getPage(stashId, pageId),
        listWorkspacePages(stashId).catch(() => [] as WorkspacePageEntry[]),
      ]);
      setStash(workspace);
      setPage(p);
      setPageIndex(index);
      if (p.folder_id) {
        const contents = await getFolderContents(stashId, p.folder_id);
        setFolderChain(contents.breadcrumbs);
      } else {
        setFolderChain([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load page");
    }
  }, [stashId, pageId]);

  const handleSave = useCallback(
    async (content: string) => {
      try {
        const updated = await updatePage(stashId, pageId, { content });
        setPage(updated);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Save failed");
      }
    },
    [stashId, pageId]
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
        <div className="mx-auto -mt-6 max-w-3xl px-12 pb-20">
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
                  {stash ? <span> in <span className="text-foreground">{stash.name}</span></span> : null}
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
                  workspaceId={stashId}
                  folderPath={folderChain.map((c) => c.name)}
                  file={page}
                  pageIndex={pageIndex}
                  onSave={handleSave}
                  onSaveStatusChange={setSaveStatus}
                  onNavigateInternal={(href) => router.push(href)}
                />
              )
            ) : (
              <p className="text-muted">Loading…</p>
            )}
          </article>
        </div>
      </div>
  );
}
