"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { downloadBlob } from "../../../../../components/DownloadMenu";
import { StashIcon } from "../../../../../components/StashIcons";
import HtmlPageView, {
  extractCommentIdsFromHtml,
  type HtmlSelectionInfo,
} from "../../../../../components/workspace/HtmlPageView";
import FileViewerHeader from "../../../../../components/workspace/FileViewerHeader";
import MarkdownEditor, {
  extractCommentIdsFromMarkdown,
  type SaveStatus,
} from "../../../../../components/workspace/MarkdownEditor";
import CommentsSidebar from "../../../../../components/workspace/CommentsSidebar";
import CommentComposerPopover from "../../../../../components/workspace/CommentComposerPopover";
import { useAuth } from "../../../../../hooks/useAuth";
import {
  createCommentThread,
  deleteCommentMessage,
  deleteCommentThread,
  getFolderContents,
  getPage,
  listCommentThreads,
  listObjectStashes,
  reconcileCommentAnchors,
  replyToCommentThread,
  setCommentResolved,
  trashItem,
  updatePage,
  type FolderBreadcrumb,
  type WorkspaceStash,
} from "../../../../../lib/api";
import type { CommentThread, Page } from "../../../../../lib/types";

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

  const [threads, setThreads] = useState<CommentThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  // Strip-anchor pulse: bumping nonce tells the editor / iframe to remove
  // the inline `<span data-comment-id>` wrapper for `id`.
  const [stripCommentToken, setStripCommentToken] = useState<{
    id: string;
    nonce: number;
  } | null>(null);
  const [htmlSelection, setHtmlSelection] = useState<HtmlSelectionInfo | null>(
    null
  );
  const htmlSelectionRef = useRef<HtmlSelectionInfo | null>(null);
  const [pendingWrapId, setPendingWrapId] = useState<string | null>(null);
  const [htmlComposer, setHtmlComposer] = useState<{
    top: number;
    left: number;
    selection: HtmlSelectionInfo;
  } | null>(null);
  const [htmlEditMode, setHtmlEditMode] = useState(false);
  const iframeBoxRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    htmlSelectionRef.current = htmlSelection;
  }, [htmlSelection]);

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

  const refreshThreads = useCallback(async () => {
    try {
      const res = await listCommentThreads(workspaceId, pageId);
      setThreads(res.threads);
    } catch {
      // Comments are non-critical — never block page rendering.
    }
  }, [workspaceId, pageId]);

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
      await refreshThreads();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load page");
    }
  }, [workspaceId, pageId, refreshThreads]);

  const reconcileAfterSave = useCallback(
    (savedContent: string, contentType: "markdown" | "html") => {
      const ids =
        contentType === "html"
          ? extractCommentIdsFromHtml(savedContent)
          : extractCommentIdsFromMarkdown(savedContent);
      reconcileCommentAnchors(workspaceId, pageId, ids)
        .then(refreshThreads)
        .catch(() => {});
    },
    [workspaceId, pageId, refreshThreads]
  );

  const handleSave = useCallback(
    async (content: string) => {
      try {
        const updated = await updatePage(workspaceId, pageId, { content });
        setPage(updated);
        reconcileAfterSave(content, "markdown");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Save failed");
      }
    },
    [workspaceId, pageId, reconcileAfterSave]
  );

  const handleHtmlMutated = useCallback(
    async (nextHtml: string) => {
      try {
        const updated = await updatePage(workspaceId, pageId, {
          content_html: nextHtml,
        });
        setPage(updated);
        reconcileAfterSave(nextHtml, "html");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Save failed");
      }
    },
    [workspaceId, pageId, reconcileAfterSave]
  );

  const handleAddCommentMarkdown = useCallback(
    async (args: {
      quoted_text: string;
      prefix: string;
      suffix: string;
      body: string;
    }) => {
      try {
        const created = await createCommentThread(workspaceId, pageId, args);
        setActiveThreadId(created.id);
        setThreads((cur) => [...cur, created]);
        return created.id;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to add comment");
        return null;
      }
    },
    [workspaceId, pageId]
  );

  const submitHtmlComment = useCallback(
    async (body: string) => {
      if (!htmlComposer) return;
      try {
        const created = await createCommentThread(workspaceId, pageId, {
          quoted_text: htmlComposer.selection.quoted_text,
          prefix: htmlComposer.selection.prefix,
          suffix: htmlComposer.selection.suffix,
          body,
        });
        setActiveThreadId(created.id);
        setThreads((cur) => [...cur, created]);
        // Ask the iframe to wrap the (still-live) selection. The iframe
        // posts back `stash:html-mutated`, which triggers handleHtmlMutated.
        setPendingWrapId(created.id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to add comment");
      } finally {
        setHtmlComposer(null);
      }
    },
    [htmlComposer, workspaceId, pageId]
  );

  const handleReply = useCallback(
    async (threadId: string, body: string) => {
      const updated = await replyToCommentThread(
        workspaceId,
        pageId,
        threadId,
        body
      );
      setThreads((cur) => cur.map((t) => (t.id === threadId ? updated : t)));
    },
    [workspaceId, pageId]
  );

  const handleSetResolved = useCallback(
    async (threadId: string, resolved: boolean) => {
      const updated = await setCommentResolved(
        workspaceId,
        pageId,
        threadId,
        resolved
      );
      setThreads((cur) => cur.map((t) => (t.id === threadId ? updated : t)));
    },
    [workspaceId, pageId]
  );

  const handleDeleteThread = useCallback(
    async (threadId: string) => {
      try {
        await deleteCommentThread(workspaceId, pageId, threadId);
        setThreads((cur) => cur.filter((t) => t.id !== threadId));
        if (activeThreadId === threadId) setActiveThreadId(null);
        // Tell the active editor to strip the inline anchor wrapper.
        setStripCommentToken({ id: threadId, nonce: Date.now() });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to delete comment");
      }
    },
    [workspaceId, pageId, activeThreadId]
  );

  const handleDeleteMessage = useCallback(
    async (threadId: string, messageId: string) => {
      try {
        const res = await deleteCommentMessage(workspaceId, pageId, messageId);
        if (res.thread_deleted) {
          setThreads((cur) => cur.filter((t) => t.id !== threadId));
          if (activeThreadId === threadId) setActiveThreadId(null);
          setStripCommentToken({ id: threadId, nonce: Date.now() });
        } else if (res.thread) {
          const updated = res.thread;
          setThreads((cur) => cur.map((t) => (t.id === threadId ? updated : t)));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to delete comment");
      }
    },
    [workspaceId, pageId, activeThreadId]
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
  const openThreadCount = threads.filter(
    (t) => !t.resolved_at && !t.orphaned
  ).length;

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
        rightExtras={
          isHtml ? (
            <button
              type="button"
              onClick={() => setHtmlEditMode((v) => !v)}
              className="rounded-md border border-border-subtle bg-raised px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised-2"
            >
              {htmlEditMode ? "Done" : "Edit"}
            </button>
          ) : undefined
        }
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
                {
                  label: "Delete",
                  destructive: true,
                  onSelect: async () => {
                    if (!window.confirm(`Move "${page.name}" to trash?`)) return;
                    try {
                      await trashItem(workspaceId, "page", pageId);
                      router.push(`/workspaces/${workspaceId}`);
                    } catch (e) {
                      setError(e instanceof Error ? e.message : "Delete failed");
                    }
                  },
                },
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
                <div ref={iframeBoxRef} className="relative">
                  <HtmlPageView
                    key={page.id}
                    html={page.content_html || ""}
                    title={page.name}
                    layout={page.html_layout}
                    onSelection={setHtmlSelection}
                    onActivateThread={setActiveThreadId}
                    activeThreadId={activeThreadId}
                    pendingWrapId={pendingWrapId}
                    onWrapComplete={() => setPendingWrapId(null)}
                    onHtmlMutated={handleHtmlMutated}
                    stripCommentToken={stripCommentToken}
                    editable={htmlEditMode}
                  />
                  {htmlSelection && !htmlComposer && !htmlEditMode && (
                    <button
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        const r = htmlSelection.rect;
                        setHtmlComposer({
                          top: r.bottom + 10,
                          left: Math.max(8, (r.left + r.right) / 2 - 130),
                          selection: htmlSelection,
                        });
                      }}
                      className="comment-anchor-pill absolute z-30 inline-flex -translate-x-1/2 -translate-y-full items-center gap-1.5 rounded-full bg-foreground px-3 py-1.5 text-[12px] font-medium text-background shadow-[0_6px_20px_-4px_rgba(0,0,0,0.35)] hover:bg-foreground/90"
                      style={{
                        top: htmlSelection.rect.top - 8,
                        left: (htmlSelection.rect.left + htmlSelection.rect.right) / 2,
                      }}
                    >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                      </svg>
                      Comment
                    </button>
                  )}
                  {htmlComposer && (
                    <CommentComposerPopover
                      top={htmlComposer.top}
                      left={htmlComposer.left}
                      onCancel={() => setHtmlComposer(null)}
                      onSubmit={submitHtmlComment}
                    />
                  )}
                </div>
              ) : (
                <MarkdownEditor
                  workspaceId={workspaceId}
                  file={page}
                  onSave={handleSave}
                  onSaveStatusChange={setSaveStatus}
                  onNavigateInternal={(href) => router.push(href)}
                  onAddComment={handleAddCommentMarkdown}
                  onActivateThread={setActiveThreadId}
                  activeThreadId={activeThreadId}
                  stripCommentToken={stripCommentToken}
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

        <div className="mt-20 hidden flex-col gap-4 lg:flex">
          <StashAside stashes={containingStashes} />
          <CommentsSidebar
            threads={threads}
            activeThreadId={activeThreadId}
            currentUserId={user.id}
            onActivate={setActiveThreadId}
            onReply={handleReply}
            onSetResolved={handleSetResolved}
            onDeleteThread={handleDeleteThread}
            onDeleteMessage={handleDeleteMessage}
          />
        </div>
      </div>
    </div>
  );
}

function StashAside({ stashes }: { stashes: WorkspaceStash[] }) {
  return (
    <aside>
      <div className="card-soft p-3.5">
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
