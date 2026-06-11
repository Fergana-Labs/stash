"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import {
  useActiveWorkspaceId,
  useShareAction,
} from "../../../../components/ShellChromeContext";
import { recordRecent } from "../../../../lib/pins";
import { PageBody } from "../../cartridges/[slug]/CartridgeItemBodies";
import {
  downloadBlob,
  downloadRenderedPdf,
  htmlToPdfBlocks,
  markdownToPdfBlocks,
} from "../../../../components/DownloadMenu";
import { DocumentPageSkeleton } from "../../../../components/SkeletonStates";
import { StashIcon } from "../../../../components/StashIcons";
import HtmlPageView, {
  extractCommentIdsFromHtml,
  type HtmlSelectionInfo,
} from "../../../../components/workspace/HtmlPageView";
import ExportDeckButton from "../../../../components/export/ExportDeckButton";
import ResourceShareButton from "../../../../components/share/ResourceShareButton";
import FileViewerHeader from "../../../../components/workspace/FileViewerHeader";
import MarkdownEditor, {
  extractCommentIdsFromMarkdown,
  type SaveStatus,
} from "../../../../components/workspace/MarkdownEditor";
import CommentsSidebar from "../../../../components/workspace/CommentsSidebar";
import CommentComposerPopover from "../../../../components/workspace/CommentComposerPopover";
import { useAuth } from "../../../../hooks/useAuth";
import {
  ApiError,
  createCommentThread,
  deleteCommentMessage,
  deleteCommentThread,
  getFolderContents,
  getPage,
  getPublicCartridge,
  listCommentThreads,
  listObjectStashes,
  reconcileCommentAnchors,
  replyToCommentThread,
  setCommentResolved,
  trashItem,
  updatePage,
  type FolderBreadcrumb,
  type PublicCartridgeItem,
  type WorkspaceCartridge,
} from "../../../../lib/api";
import type { CommentThread, Page } from "../../../../lib/types";
import { subscribePageEvents } from "../../../../lib/pageEvents";

function wrapHtml(title: string, body: string): string {
  // HTML pages can be stored as a full document (when imported from .html
  // uploads) — wrapping again would nest <html> inside <html>.
  if (/^\s*(<!doctype|<html[\s>])/i.test(body)) return body;
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(
    title
  )}</title><style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2em auto;padding:0 1em;line-height:1.6;color:#1a1a1a}h1,h2,h3{line-height:1.25}pre{background:#f6f6f6;padding:1em;overflow:auto;border-radius:6px}code{background:#f6f6f6;padding:.1em .3em;border-radius:3px}</style></head><body>${body}</body></html>`;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" : c === '"' ? "&quot;" : "&#39;"
  );
}

function readCommentAnchorTops(
  container: HTMLElement,
  relativeTo: HTMLElement,
): Record<string, number> {
  const rootRect = relativeTo.getBoundingClientRect();
  const next: Record<string, number> = {};
  const anchors = container.querySelectorAll<HTMLElement>("[data-comment-id]");
  anchors.forEach((anchor) => {
    const id = anchor.getAttribute("data-comment-id");
    if (!id) return;
    const rects = anchor.getClientRects();
    const rect = rects[0] ?? anchor.getBoundingClientRect();
    const top = Math.max(0, Math.round(rect.top - rootRect.top));
    if (next[id] === undefined || top < next[id]) next[id] = top;
  });
  return next;
}

function sameAnchorTops(a: Record<string, number>, b: Record<string, number>): boolean {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) return false;
  return aKeys.every((key) => a[key] === b[key]);
}

export default function StashPageView() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const pageId = params.pageId as string;
  const { user, loading } = useAuth();
  // When ?stash=<slug> is present, the page is viewed through a stash —
  // the viewer might not be a workspace member, so we fall back to the
  // public-stash payload for read-only rendering.
  const stashSlug = searchParams.get("stash");

  const [page, setPage] = useState<Page | null>(null);
  // Empty until the page loads — every consumer below renders or fires
  // only after that.
  const workspaceId = page?.workspace_id ?? "";
  useActiveWorkspaceId(workspaceId || null);
  const [folderChain, setFolderChain] = useState<FolderBreadcrumb[]>([]);
  const [containingStashes, setContainingStashes] = useState<WorkspaceCartridge[]>([]);
  const [stashFallback, setStashFallback] = useState<
    { stash: WorkspaceCartridge; item: PublicCartridgeItem } | null
  >(null);
  const [stashAccessDenied, setStashAccessDenied] = useState(false);
  // Anonymous viewer reading a publicly-shared page (anyone with the link).
  const [publicView, setPublicView] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [error, setError] = useState("");
  // Save responses can arrive out of order if a fast save fires while a
  // slow save is still in flight. Treat the most-recently-issued seq as
  // the source of truth so older responses can't roll back the page.
  const saveSeq = useRef(0);
  const pageLayoutRef = useRef<HTMLDivElement | null>(null);
  const articleRef = useRef<HTMLElement | null>(null);
  const [commentAnchorTops, setCommentAnchorTops] = useState<Record<string, number>>({});

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

  useEffect(() => {
    setCommentAnchorTops({});
    setExternalEdit(null);
  }, [workspaceId, pageId]);

  // Live updates: when an agent or another user edits this page on the backend,
  // refresh a passive view in place (HTML / read-only), or — when the user is
  // actively editing — surface a non-destructive "reload" banner rather than
  // clobber their buffer.
  const [contentVersion, setContentVersion] = useState(0);
  const [externalEdit, setExternalEdit] = useState<{ agentName: string | null } | null>(null);
  const liveViewRef = useRef({ isHtml: false, htmlEditMode: false });
  const loadRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    if (!user || stashSlug || !workspaceId) return;
    return subscribePageEvents(workspaceId, (evt) => {
      if (evt.page_id !== pageId) return;
      const { isHtml, htmlEditMode } = liveViewRef.current;
      if (isHtml && !htmlEditMode) {
        loadRef.current();
        setContentVersion((v) => v + 1);
      } else {
        setExternalEdit({ agentName: evt.agent_name });
      }
    });
  }, [workspaceId, pageId, user, stashSlug]);

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

  const shareAction = useMemo(() => {
    if (!page || stashSlug || !user) return null;
    const title = page.name.replace(/\.md$/, "");
    return (
      <ResourceShareButton
        objectType="page"
        objectId={page.id}
        resourceName={title}
        resourceUrlPath={`/p/${page.id}`}
        currentUser={user}
      />
    );
  }, [page, stashSlug, user]);
  useShareAction(shareAction);

  const refreshThreads = useCallback(
    async (ws: string = workspaceId) => {
      if (!ws) return;
      try {
        const res = await listCommentThreads(ws, pageId);
        setThreads(res.threads);
      } catch {
        // Comments are non-critical — never block page rendering.
      }
    },
    [workspaceId, pageId]
  );

  const loadStashFallback = useCallback(async () => {
    if (!stashSlug) return false;
    try {
      const data = await getPublicCartridge(stashSlug);
      const item = data.items.find(
        (it) => it.object_type === "page" && it.object_id === pageId,
      );
      if (!item) {
        setStashFallback(null);
        setStashAccessDenied(true);
        setError("");
        return true;
      }
      setStashFallback({ stash: data.cartridge, item });
      setStashAccessDenied(false);
      setError("");
      return true;
    } catch {
      setStashFallback(null);
      setStashAccessDenied(true);
      setError("");
      return true;
    }
  }, [stashSlug, pageId]);

  const load = useCallback(async () => {
    let p;
    try {
      p = await getPage(pageId);
    } catch (e) {
      // Non-members of the workspace fall back to the stash payload when
      // a ?stash=<slug> hint is present. The stash's readability check is
      // the only authorization in that path.
      if (
        stashSlug &&
        e instanceof ApiError &&
        (e.status === 401 || e.status === 403 || e.status === 404)
      ) {
        if (await loadStashFallback()) return;
      }
      setError(e instanceof Error ? e.message : "Failed to load page");
      return;
    }
    // getPage is the authorization gate (member OR share OR cartridge). The
    // rest is enrichment — a shared viewer may not have access to every related
    // resource (folder, containing cartridges), and that must never blank the
    // page they were legitimately shared.
    setPage(p);
    setStashFallback(null);
    setStashAccessDenied(false);
    setError("");
    recordRecent(p.workspace_id, pageId, "page");
    listObjectStashes(p.workspace_id, "page", pageId)
      .then(setContainingStashes)
      .catch(() => {});
    if (p.folder_id) {
      getFolderContents(p.workspace_id, p.folder_id)
        .then((contents) => setFolderChain(contents.breadcrumbs))
        .catch(() => setFolderChain([]));
    } else {
      setFolderChain([]);
    }
    refreshThreads(p.workspace_id).catch(() => {});
  }, [pageId, refreshThreads, stashSlug, loadStashFallback]);

  const reconcileAfterSave = useCallback(
    (savedContent: string, contentType: "markdown" | "html") => {
      const ids =
        contentType === "html"
          ? extractCommentIdsFromHtml(savedContent)
          : extractCommentIdsFromMarkdown(savedContent);
      reconcileCommentAnchors(workspaceId, pageId, ids)
        .then(() => refreshThreads())
        .catch(() => {});
    },
    [workspaceId, pageId, refreshThreads]
  );

  const handleSave = useCallback(
    async (content: string) => {
      const seq = saveSeq.current + 1;
      saveSeq.current = seq;
      try {
        const updated = await updatePage(workspaceId, pageId, {
          content,
          collab_projection: true,
        });
        if (saveSeq.current === seq) setPage(updated);
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

  // Anonymous viewer, no stash hint: the page may carry a public (anyone
  // with the link) grant. Try the canonical endpoint; bounce to login only
  // when it 404s.
  const loadPublic = useCallback(async () => {
    try {
      const p = await getPage(pageId);
      setPage(p);
      setPublicView(true);
      setError("");
    } catch {
      router.push("/login");
    }
  }, [pageId, router]);

  useEffect(() => {
    // Anonymous viewers can load this page via ?stash=<slug> (the stash
    // payload is the read source) or via a public grant on the page itself.
    // Authenticated viewers always try the workspace endpoint first.
    if (loading) return;
    if (user) load();
    else if (stashSlug) void loadStashFallback();
    else void loadPublic();
  }, [user, loading, load, loadStashFallback, loadPublic, stashSlug]);

  const handleHtmlAnchorTops = useCallback((iframeAnchorTops: Record<string, number>) => {
    const layout = pageLayoutRef.current;
    const iframeBox = iframeBoxRef.current;
    if (!layout || !iframeBox) return;
    const offset = iframeBox.getBoundingClientRect().top - layout.getBoundingClientRect().top;
    const next: Record<string, number> = {};
    for (const [id, top] of Object.entries(iframeAnchorTops)) {
      next[id] = Math.max(0, Math.round(offset + top));
    }
    setCommentAnchorTops((current) => (sameAnchorTops(current, next) ? current : next));
  }, []);

  useLayoutEffect(() => {
    if (!page || page.content_type === "html") return;
    const article = articleRef.current;
    const layout = pageLayoutRef.current;
    if (!article || !layout) return;

    const update = () => {
      const next = readCommentAnchorTops(article, layout);
      setCommentAnchorTops((current) => (sameAnchorTops(current, next) ? current : next));
    };

    update();
    const resizeObserver =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    resizeObserver?.observe(article);

    const mutationObserver =
      typeof MutationObserver === "undefined"
        ? null
        : new MutationObserver(update);
    mutationObserver?.observe(article, {
      attributes: true,
      attributeFilter: ["data-comment-id"],
      childList: true,
      subtree: true,
    });

    window.addEventListener("resize", update);
    return () => {
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [page]);

  if (loading) return <DocumentPageSkeleton />;
  if (publicView && page) {
    return <PublicPageView page={page} />;
  }
  if (stashFallback) {
    return (
      <StashFallbackPageView
        stashSlug={stashSlug ?? ""}
        stashTitle={stashFallback.stash.title}
        item={stashFallback.item}
      />
    );
  }
  if (stashAccessDenied) {
    return <PageAccessDeniedScreen accountLabel={user?.email ?? user?.name ?? null} />;
  }
  if (!user) {
    // Public-grant probe in flight, or the login bounce is already firing.
    if (!stashSlug) return <DocumentPageSkeleton />;
    // Stash mode: waiting on the fallback to land, or it failed.
    if (!error) return <DocumentPageSkeleton />;
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="font-display text-[24px] font-bold text-foreground">Page unavailable</h1>
        <p className="mt-2 text-[14px] leading-relaxed text-dim">{error}</p>
      </div>
    );
  }
  if (!page && !error) return <DocumentPageSkeleton />;

  const isHtml = page?.content_type === "html";
  // Keep the live-update handler reading current view state without resubscribing.
  liveViewRef.current = { isHtml, htmlEditMode };
  loadRef.current = load;
  const updatedAt = page?.updated_at
    ? new Date(page.updated_at).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

  const baseName = page ? page.name.replace(/\.(md|html)$/i, "") : "";
  const pdfSubtitle = updatedAt ? `Last edited ${updatedAt}` : undefined;

  // Provenance: when an agent made the last content edit, link the page back to
  // the chat session that produced it.
  const metaItems: ReactNode[] = [];
  if (updatedAt) metaItems.push(`Last edited ${updatedAt}`);
  if (page?.last_edit_agent_name && page.last_edit_session_id) {
    metaItems.push(
      <Link
        key="provenance"
        href={`/workspaces/${workspaceId}/sessions?session=${encodeURIComponent(
          page.last_edit_session_id,
        )}`}
        className="underline decoration-dotted underline-offset-2 hover:text-[var(--text)]"
      >
        Edited by {page.last_edit_agent_name}
      </Link>,
    );
  }
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <FileViewerHeader
        icon={isHtml ? <HtmlGlyph /> : <PageGlyph />}
        iconColor={isHtml ? "var(--color-brand-600)" : "var(--text-muted)"}
        title={baseName}
        onRenameTitle={
          page
            ? async (next) => {
                // Preserve the file extension so the backend's kind
                // detection (and the listing UI's icons) keep working.
                const extension = page.content_type === "html" ? ".html" : ".md";
                const newName = next.toLowerCase().endsWith(extension) ? next : `${next}${extension}`;
                const updated = await updatePage(workspaceId, pageId, { name: newName });
                setPage(updated);
                return updated.name.replace(/\.(md|html)$/i, "");
              }
            : undefined
        }
        tags={isHtml ? [{ label: "html", tone: "brand" }] : undefined}
        meta={metaItems.length ? metaItems : undefined}
        saveStatus={page && !isHtml ? saveStatus : null}
        rightExtras={
          isHtml ? (
            <div className="flex items-center gap-2">
              {page && (
                <ExportDeckButton
                  pageId={page.id}
                  layout={page.html_layout}
                  contentType={page.content_type}
                />
              )}
              <button
                type="button"
                onClick={() => setHtmlEditMode((v) => !v)}
                className="rounded-md border border-border-subtle bg-raised px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised-2"
              >
                {htmlEditMode ? "Done" : "Edit"}
              </button>
            </div>
          ) : undefined
        }
        downloadOptions={
          page
            ? [
                ...(isHtml
                  ? [
                      {
                        label: "HTML (.html)",
                        onSelect: () =>
                          downloadBlob(
                            wrapHtml(baseName, page.content_html ?? ""),
                            "text/html",
                            `${baseName}.html`
                          ),
                      },
                      {
                        label: "PDF (.pdf)",
                        onSelect: () =>
                          downloadRenderedPdf({
                            title: baseName,
                            subtitle: pdfSubtitle,
                            blocks: htmlToPdfBlocks(page.content_html ?? ""),
                            filename: `${baseName}.pdf`,
                          }),
                      },
                    ]
                  : [
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
                        label: "PDF (.pdf)",
                        onSelect: () =>
                          downloadRenderedPdf({
                            title: baseName,
                            subtitle: pdfSubtitle,
                            blocks: markdownToPdfBlocks(page.content_markdown ?? ""),
                            filename: `${baseName}.pdf`,
                          }),
                      },
                    ]),
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
      <div
        ref={pageLayoutRef}
        className="mx-auto mt-6 grid max-w-[1200px] gap-7 px-12 pb-20 lg:grid-cols-[minmax(0,1fr)_240px]"
      >
        <main className="min-w-0">
          {externalEdit && (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-[var(--color-brand-600)]/40 bg-[var(--color-brand-600)]/10 px-4 py-2 text-[13px]">
              <span>
                This page was edited{" "}
                {externalEdit.agentName ? `by ${externalEdit.agentName}` : "externally"} — reload to
                see the latest.
              </span>
              <span className="flex shrink-0 items-center gap-3">
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="font-medium text-[var(--color-brand-600)] hover:underline"
                >
                  Reload
                </button>
                <button
                  type="button"
                  onClick={() => setExternalEdit(null)}
                  className="text-[var(--text-muted)] hover:text-foreground"
                >
                  Dismiss
                </button>
              </span>
            </div>
          )}
          {error && (
            <div className="mb-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          <article ref={articleRef} className="text-[15px] leading-relaxed text-foreground">
            {page ? (
              isHtml ? (
                <div ref={iframeBoxRef} className="relative">
                  <HtmlPageView
                    key={`${page.id}:${contentVersion}`}
                    html={page.content_html || ""}
                    title={page.name}
                    layout={page.html_layout}
                    onSelection={setHtmlSelection}
                    onActivateThread={setActiveThreadId}
                    onAnchorTops={handleHtmlAnchorTops}
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
                  collaborationUser={{
                    id: user.id,
                    name: user.display_name || user.name,
                  }}
                  onSaveStatusChange={setSaveStatus}
                  onNavigateInternal={(href) => router.push(href)}
                  onAddComment={handleAddCommentMarkdown}
                  onActivateThread={setActiveThreadId}
                  activeThreadId={activeThreadId}
                  stripCommentToken={stripCommentToken}
                />
              )
            ) : null}
          </article>
        </main>

        <div className="hidden lg:block">
          <CommentsSidebar
            threads={threads}
            activeThreadId={activeThreadId}
            currentUserId={user.id}
            anchorTops={commentAnchorTops}
            onActivate={setActiveThreadId}
            onReply={handleReply}
            onSetResolved={handleSetResolved}
            onDeleteThread={handleDeleteThread}
            onDeleteMessage={handleDeleteMessage}
          />
          <div className={threads.length > 0 ? "mt-6" : "mt-20"}>
            <StashAside stashes={containingStashes} />
          </div>
        </div>
      </div>
    </div>
  );
}

function PageAccessDeniedScreen({ accountLabel }: { accountLabel: string | null }) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="flex h-14 items-center border-b border-border bg-surface px-5">
        <div className="flex items-center gap-2.5">
          <span className="text-[var(--color-brand-600)]">
            <AccessPageGlyph />
          </span>
          <span className="font-display text-[18px] font-semibold text-foreground">Stash</span>
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center px-6 py-16">
        <section className="w-full max-w-[520px] text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-lg border border-border bg-brand-100 text-[var(--color-brand-700)] shadow-sm">
            <AccessPageGlyph large />
          </div>
          <h1 className="mt-6 font-display text-[28px] font-semibold leading-tight tracking-tight text-foreground">
            You don&apos;t have access to this page
          </h1>
          <p className="mt-3 text-[14px] leading-6 text-dim">
            If someone sent you this link, ask them to share the Stash with your
            account.
          </p>
          {accountLabel ? (
            <p className="mt-4 text-[13px] leading-5 text-muted">
              You&apos;re signed in as <span className="font-medium text-foreground">{accountLabel}</span>.
            </p>
          ) : null}
          <div className="mt-8 flex justify-center">
            <Link
              href="/"
              className="inline-flex h-9 items-center justify-center rounded-md bg-[var(--color-brand-600)] px-6 text-[14px] font-medium text-white hover:bg-[var(--color-brand-700)]"
            >
              Go to home
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}

function AccessPageGlyph({ large = false }: { large?: boolean }) {
  const size = large ? 34 : 24;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h4" />
    </svg>
  );
}

function StashAside({ stashes }: { stashes: WorkspaceCartridge[] }) {
  return (
    <aside>
      <div className="card-soft p-3.5">
        <div className="sys-label">In Stashes</div>
        {stashes.length > 0 ? (
          <div className="mt-2 flex flex-col gap-1.5">
            {stashes.map((stash) => (
              <Link
                key={stash.id}
                href={`/cartridges/${stash.slug}`}
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

// Read-only render for viewers who can't reach the workspace endpoint —
// usually because they aren't a workspace member. The content comes from
// the public-stash payload, gated by the stash's readability rules.
function PublicPageView({ page }: { page: Page }) {
  const item = {
    object_type: "page",
    object_id: page.id,
    label: page.name,
    inline: { page },
  } as unknown as PublicCartridgeItem;
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <h1 className="m-0 font-display text-[22px] font-bold leading-tight tracking-[-0.015em] text-foreground">
          {page.name.replace(/\.(md|html)$/i, "")}
        </h1>
        <div className="mt-1 text-[11.5px] uppercase tracking-wide text-muted">
          page · shared with link
        </div>
        <div className="mt-6">
          <PageBody item={item} />
        </div>
      </div>
    </div>
  );
}

function StashFallbackPageView({
  stashSlug,
  stashTitle,
  item,
}: {
  stashSlug: string;
  stashTitle: string;
  item: PublicCartridgeItem;
}) {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <Link
          href={`/cartridges/${stashSlug}`}
          className="inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-foreground"
        >
          ← {stashTitle}
        </Link>
        <h1 className="mt-3 m-0 font-display text-[22px] font-bold leading-tight tracking-[-0.015em] text-foreground">
          {item.label || "(untitled)"}
        </h1>
        <div className="mt-1 text-[11.5px] uppercase tracking-wide text-muted">
          page · read-only via Stash
        </div>
        <div className="mt-6">
          <PageBody item={item} />
        </div>
      </div>
    </div>
  );
}
