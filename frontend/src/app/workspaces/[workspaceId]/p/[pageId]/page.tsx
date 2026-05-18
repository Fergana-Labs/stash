"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { downloadBlob } from "../../../../../components/DownloadMenu";
import { StashIcon } from "../../../../../components/StashIcons";
import HtmlPageView from "../../../../../components/workspace/HtmlPageView";
import FileViewerHeader from "../../../../../components/workspace/FileViewerHeader";
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
  const { user, loading } = useAuth();

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

  const isHtml = page?.content_type === "html";
  const updatedAt = page?.updated_at
    ? new Date(page.updated_at).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

  const baseName = page ? page.name.replace(/\.md$/i, "") : "";

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <FileViewerHeader
        icon={isHtml ? <HtmlGlyph /> : <PageGlyph />}
        iconColor={isHtml ? "var(--color-brand-600)" : "var(--text-muted)"}
        title={baseName}
        onRenameTitle={
          page
            ? async (next) => {
                // Preserve the .md suffix on markdown pages so the
                // backend's file kind detection keeps working.
                const had = page.name.toLowerCase().endsWith(".md");
                const newName = had && !next.toLowerCase().endsWith(".md") ? `${next}.md` : next;
                const updated = await updatePage(workspaceId, pageId, { name: newName });
                setPage(updated);
                return updated.name.replace(/\.md$/i, "");
              }
            : undefined
        }
        tags={isHtml ? [{ label: "html", tone: "brand" }] : undefined}
        meta={updatedAt ? [`Last edited ${updatedAt}`] : undefined}
        saveStatus={page && !isHtml ? saveStatus : null}
        downloadOptions={
          page
            ? [
                {
                  label: "Markdown (.md)",
                  onSelect: () =>
                    downloadBlob(
                      page.content_markdown ?? "",
                      "text/markdown",
                      `${baseName}.md`
                    ),
                },
                {
                  label: "HTML (.html)",
                  onSelect: () =>
                    downloadBlob(
                      wrapHtml(page.name, page.content_html ?? ""),
                      "text/html",
                      `${baseName}.html`
                    ),
                },
                { label: "PDF (print)", onSelect: () => window.print() },
              ]
            : undefined
        }
      />
      <div className="mx-auto mt-6 grid max-w-[1100px] gap-7 px-12 pb-20 lg:grid-cols-[minmax(0,1fr)_240px]">
        <main className="min-w-0">
          {error && (
            <div className="mb-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          <article className="text-[15px] leading-relaxed text-foreground">
            {page ? (
              isHtml ? (
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

          {page && !isHtml && (
            <div className="mt-6 flex items-center gap-2 rounded-lg border border-dashed border-border bg-surface px-3 py-2.5 text-[12.5px] text-muted">
              <span className="font-mono text-dim">/</span>
              <span>
                press <KeyHint>/</KeyHint> for blocks · <KeyHint>@</KeyHint> for pages or
                people · <KeyHint>⌘+J</KeyHint> to ask the workspace
              </span>
            </div>
          )}
        </main>

        <StashAside stashes={containingStashes} />
      </div>
    </div>
  );
}

function StashAside({ stashes }: { stashes: WorkspaceStash[] }) {
  return (
    <aside className="mt-20 hidden lg:block">
      <div className="card-soft sticky top-16 p-3.5">
        <div className="sys-label">In Stashes</div>
        {stashes.length > 0 ? (
          <div className="mt-2 flex flex-col gap-1.5">
            {stashes.map((stash) => (
              <Link
                key={stash.id}
                href={`/stashes/${stash.slug}`}
                className="linkrow px-2 py-1.5"
              >
                <span className="text-[var(--color-brand-600)]">
                  <StashIcon />
                </span>
                <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-foreground">
                  {stash.title}
                </span>
                <span className="sys-label" style={{ fontSize: 10 }}>
                  {stash.items.length}
                </span>
              </Link>
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

function KeyHint({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-[3px] bg-raised px-[5px] font-mono text-[11px] text-dim">
      {children}
    </span>
  );
}

function PageGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h4" />
    </svg>
  );
}

function HtmlGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18" />
      <circle cx="6" cy="6.5" r="0.6" fill="currentColor" />
      <circle cx="8.2" cy="6.5" r="0.6" fill="currentColor" />
    </svg>
  );
}
