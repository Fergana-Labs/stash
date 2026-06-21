"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { useShareAction } from "@/components/ShellChromeContext";
import { recordRecent } from "@/lib/pins";
import { PageBody } from "../../skills/[slug]/SkillItemBodies";
import {
  downloadBlob,
  downloadRenderedPdf,
  htmlToPdfBlocks,
  markdownToPdfBlocks,
} from "@/components/DownloadMenu";
import { DocumentPageSkeleton } from "@/components/SkeletonStates";
import HtmlPageView, {
  extractCommentIdsFromHtml,
  type HtmlSelectionInfo,
} from "@/components/workspace/HtmlPageView";
import ExportDeckButton from "@/components/export/ExportDeckButton";
import ResourceShareButton from "@/components/share/ResourceShareButton";
import FileViewerHeader from "@/components/workspace/FileViewerHeader";
import MarkdownEditor, {
  extractCommentIdsFromMarkdown,
  type SaveStatus,
} from "@/components/workspace/MarkdownEditor";
import CommentsSidebar from "@/components/workspace/CommentsSidebar";
import CommentComposerPopover from "@/components/workspace/CommentComposerPopover";
import { useAuth } from "@/hooks/useAuth";
import {
  ApiError,
  createCommentThread,
  createPage,
  deleteCommentMessage,
  deleteCommentThread,
  getFolderContents,
  getPage,
  getPublicSkill,
  listCommentThreads,
  reconcileCommentAnchors,
  replyToCommentThread,
  setCommentResolved,
  trashItem,
  updatePage,
  type FolderBreadcrumb,
  type PublicSkillPage,
} from "@/lib/api";
import { findInSkillContents } from "@/lib/localSkill";
import type { CommentThread, Page } from "@/lib/types";
import { subscribePageEvents } from "@/lib/pageEvents";
import { refreshSidebar } from "@/lib/skillNavigationCache";

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

export default function SkillPageView() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const confirm = useConfirm();
  const pageId = params.pageId as string;
  const { user, loading } = useAuth();
  // When ?skill=<slug> is present, the page is viewed through a skill —
  // the viewer might not own the page, so we fall back to the
  // public-skill payload for read-only rendering.
  const skillSlug = searchParams.get("skill");

  const [page, setPage] = useState<Page | null>(null);
  // The scope is the current user. Empty until auth resolves — every
  // consumer below renders or fires only after that.
  const scopeId = user?.id ?? "";
  const [folderChain, setFolderChain] = useState<FolderBreadcrumb[]>([]);
  const [skillFallback, setSkillFallback] = useState<
    { skillTitle: string; page: PublicSkillPage } | null
  >(null);
  const [skillAccessDenied, setSkillAccessDenied] = useState(false);
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

  // Deselect the active comment when clicking anywhere outside its anchor in
  // the page and its card in the sidebar.
  useEffect(() => {
    if (!activeThreadId) return;
    function handlePointerDown(event: MouseEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.closest?.("[data-comment-id], [data-comment-thread-id]")) return;
      setActiveThreadId(null);
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [activeThreadId]);

  useEffect(() => {
    setCommentAnchorTops({});
    setExternalEdit(null);
  }, [pageId]);

  // Live updates: when an agent or another user edits this page on the backend,
  // refresh a passive view in place (HTML / read-only), or — when the user is
  // actively editing — surface a non-destructive "reload" banner rather than
  // clobber their buffer.
  const [contentVersion, setContentVersion] = useState(0);
  const [externalEdit, setExternalEdit] = useState<{ agentName: string | null } | null>(null);
  const liveViewRef = useRef({ isHtml: false, htmlEditMode: false });
  const loadRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    if (!user || skillSlug) return;
    return subscribePageEvents((evt) => {
      if (evt.page_id !== pageId) return;
      const { isHtml, htmlEditMode } = liveViewRef.current;
      if (isHtml && !htmlEditMode) {
        loadRef.current();
        setContentVersion((v) => v + 1);
      } else {
        setExternalEdit({ agentName: evt.agent_name });
      }
    });
  }, [scopeId, pageId, user, skillSlug]);

  useBreadcrumbs(
    [
      ...folderChain.map((c) => ({
        label: c.name,
        href: `/folders/${c.id}`,
      })),
      { label: page ? page.name.replace(/\.md$/, "") : "Page" },
    ],
    `page/${pageId}/${page?.name ?? ""}/${folderChain.map((c) => c.id).join(",")}`
  );

  const shareAction = useMemo(() => {
    if (!page || skillSlug || !user) return null;
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
  }, [page, skillSlug, user]);
  useShareAction(shareAction);

  const refreshThreads = useCallback(async () => {
    try {
      const res = await listCommentThreads(pageId);
      setThreads(res.threads);
    } catch {
      // Comments are non-critical — never block page rendering.
    }
  }, [pageId]);

  const loadSkillFallback = useCallback(async () => {
    if (!skillSlug) return false;
    try {
      const data = await getPublicSkill(skillSlug);
      const page = findInSkillContents(data.contents, "page", pageId);
      if (!page) {
        setSkillFallback(null);
        setSkillAccessDenied(true);
        setError("");
        return true;
      }
      setSkillFallback({ skillTitle: data.skill.title, page });
      setSkillAccessDenied(false);
      setError("");
      return true;
    } catch {
      setSkillFallback(null);
      setSkillAccessDenied(true);
      setError("");
      return true;
    }
  }, [skillSlug, pageId]);

  const load = useCallback(async () => {
    let p;
    try {
      p = await getPage(pageId);
    } catch (e) {
      // Viewers who don't own the page fall back to the skill payload when
      // a ?skill=<slug> hint is present. The skill's readability check is
      // the only authorization in that path.
      if (
        skillSlug &&
        e instanceof ApiError &&
        (e.status === 401 || e.status === 403 || e.status === 404)
      ) {
        if (await loadSkillFallback()) return;
      }
      setError(e instanceof Error ? e.message : "Failed to load page");
      return;
    }
    // getPage is the authorization gate (owner OR share OR skill). The
    // rest is enrichment — a shared viewer may not have access to every related
    // resource (folder, containing skills), and that must never blank the
    // page they were legitimately shared.
    setPage(p);
    setSkillFallback(null);
    setSkillAccessDenied(false);
    setError("");
    recordRecent(pageId, "page");
    if (p.folder_id) {
      getFolderContents(p.folder_id)
        .then((contents) => setFolderChain(contents.breadcrumbs))
        .catch(() => setFolderChain([]));
    } else {
      setFolderChain([]);
    }
    refreshThreads().catch(() => {});
  }, [pageId, refreshThreads, skillSlug, loadSkillFallback]);

  const reconcileAfterSave = useCallback(
    (savedContent: string, contentType: "markdown" | "html") => {
      const ids =
        contentType === "html"
          ? extractCommentIdsFromHtml(savedContent)
          : extractCommentIdsFromMarkdown(savedContent);
      reconcileCommentAnchors(pageId, ids)
        .then(() => refreshThreads())
        .catch(() => {});
    },
    [pageId, refreshThreads]
  );

  const handleSave = useCallback(
    async (content: string) => {
      const seq = saveSeq.current + 1;
      saveSeq.current = seq;
      try {
        const updated = await updatePage(pageId, {
          content,
          collab_projection: true,
        });
        if (saveSeq.current === seq) setPage(updated);
        reconcileAfterSave(content, "markdown");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Save failed");
      }
    },
    [pageId, reconcileAfterSave]
  );

  const handleHtmlMutated = useCallback(
    async (nextHtml: string) => {
      try {
        const updated = await updatePage(pageId, {
          content_html: nextHtml,
        });
        setPage(updated);
        reconcileAfterSave(nextHtml, "html");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Save failed");
      }
    },
    [pageId, reconcileAfterSave]
  );

  const handleAddCommentMarkdown = useCallback(
    async (args: {
      quoted_text: string;
      prefix: string;
      suffix: string;
      body: string;
    }) => {
      try {
        const created = await createCommentThread(pageId, args);
        setActiveThreadId(created.id);
        setThreads((cur) => [...cur, created]);
        return created.id;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to add comment");
        return null;
      }
    },
    [pageId]
  );

  const submitHtmlComment = useCallback(
    async (body: string) => {
      if (!htmlComposer) return;
      try {
        const created = await createCommentThread(pageId, {
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
    [htmlComposer, pageId]
  );

  const handleReply = useCallback(
    async (threadId: string, body: string) => {
      const updated = await replyToCommentThread(pageId, threadId, body);
      setThreads((cur) => cur.map((t) => (t.id === threadId ? updated : t)));
    },
    [pageId]
  );

  const handleSetResolved = useCallback(
    async (threadId: string, resolved: boolean) => {
      const updated = await setCommentResolved(pageId, threadId, resolved);
      setThreads((cur) => cur.map((t) => (t.id === threadId ? updated : t)));
    },
    [pageId]
  );

  const handleDeleteThread = useCallback(
    async (threadId: string) => {
      try {
        await deleteCommentThread(pageId, threadId);
        setThreads((cur) => cur.filter((t) => t.id !== threadId));
        if (activeThreadId === threadId) setActiveThreadId(null);
        // Tell the active editor to strip the inline anchor wrapper.
        setStripCommentToken({ id: threadId, nonce: Date.now() });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to delete comment");
      }
    },
    [pageId, activeThreadId]
  );

  const handleDeleteMessage = useCallback(
    async (threadId: string, messageId: string) => {
      try {
        const res = await deleteCommentMessage(pageId, messageId);
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
    [pageId, activeThreadId]
  );

  useEffect(() => {
    // Anonymous viewers can load this page when ?skill=<slug> is set —
    // the skill payload is the read source. Authenticated viewers always
    // try the canonical page endpoint first.
    if (user) load();
    else if (!loading && skillSlug) void loadSkillFallback();
  }, [user, loading, load, loadSkillFallback, skillSlug]);

  useEffect(() => {
    // Only bounce to login if there's no skill fallback path available.
    if (!loading && !user && !skillSlug) router.push("/login");
  }, [user, loading, router, skillSlug]);

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
  if (skillFallback) {
    return (
      <SkillFallbackPageView
        skillSlug={skillSlug ?? ""}
        skillTitle={skillFallback.skillTitle}
        page={skillFallback.page}
      />
    );
  }
  if (skillAccessDenied) {
    return <PageAccessDeniedScreen accountLabel={user?.email ?? user?.name ?? null} />;
  }
  if (!user) {
    // Login bounce is already firing for the no-skill case.
    if (!skillSlug) return null;
    // Skill mode: waiting on the fallback to land, or it failed.
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
  // Full-width HTML drops the 1200px reading-column cap so the page gets the
  // whole window (minus the comment rail) — room for real responsive layouts.
  const isFullWidth = isHtml && page?.html_layout === "full-width";
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

  async function handleNewPage() {
    if (!page) return;
    try {
      const created = await createPage("Untitled", page.folder_id);
      refreshSidebar().catch(() => {});
      router.push(`/p/${created.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create page");
    }
  }

  // Provenance: when an agent made the last content edit, link the page back to
  // the chat session that produced it.
  const metaItems: ReactNode[] = [];
  if (updatedAt) metaItems.push(`Last edited ${updatedAt}`);
  if (page?.last_edit_agent_name && page.last_edit_session_id) {
    metaItems.push(
      <Link
        key="provenance"
        href={`/sessions?session=${encodeURIComponent(
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
                const updated = await updatePage(pageId, { name: newName });
                setPage(updated);
                return updated.name.replace(/\.(md|html)$/i, "");
              }
            : undefined
        }
        tags={isHtml ? [{ label: "html", tone: "brand" }] : undefined}
        meta={metaItems.length ? metaItems : undefined}
        saveStatus={page && !isHtml ? saveStatus : null}
        rightExtras={
          page ? (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleNewPage}
                className="cursor-pointer rounded-md border border-border-subtle bg-raised px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised-2"
              >
                + New page
              </button>
              {isHtml && (
                <ExportDeckButton
                  pageId={page.id}
                  layout={page.html_layout}
                  contentType={page.content_type}
                />
              )}
              {isHtml && (
                <button
                  type="button"
                  onClick={() => setHtmlEditMode((v) => !v)}
                  className="cursor-pointer rounded-md border border-border-subtle bg-raised px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised-2"
                >
                  {htmlEditMode ? "Done" : "Edit"}
                </button>
              )}
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
                    const ok = await confirm({
                      title: `Move "${page.name}" to trash?`,
                      confirmLabel: "Move to trash",
                    });
                    if (!ok) return;
                    try {
                      await trashItem("page", pageId);
                      router.push("/");
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
        className={`mt-6 grid gap-7 px-12 pb-20 lg:grid-cols-[minmax(0,1fr)_240px] ${
          isFullWidth ? "" : "mx-auto max-w-[1200px]"
        }`}
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
                  className="cursor-pointer font-medium text-[var(--color-brand-600)] hover:underline"
                >
                  Reload
                </button>
                <button
                  type="button"
                  onClick={() => setExternalEdit(null)}
                  className="cursor-pointer text-[var(--text-muted)] hover:text-foreground"
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
                      className="comment-anchor-pill absolute z-30 inline-flex -translate-x-1/2 -translate-y-full cursor-pointer items-center gap-1.5 rounded-full bg-foreground px-3 py-1.5 text-[12px] font-medium text-background shadow-[0_6px_20px_-4px_rgba(0,0,0,0.35)] hover:bg-foreground/90"
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
            If someone sent you this link, ask them to share the Skill with your
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

// Read-only render for viewers who can't reach the canonical page endpoint —
// usually because they don't own the page. The content comes from
// the public-skill payload, gated by the skill's readability rules.
function SkillFallbackPageView({
  skillSlug,
  skillTitle,
  page,
}: {
  skillSlug: string;
  skillTitle: string;
  page: PublicSkillPage;
}) {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <Link
          href={`/skills/${skillSlug}`}
          className="inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-foreground"
        >
          ← {skillTitle}
        </Link>
        <h1 className="mt-3 m-0 font-display text-[22px] font-bold leading-tight tracking-[-0.015em] text-foreground">
          {page.name || "(untitled)"}
        </h1>
        <div className="mt-1 text-[11.5px] uppercase tracking-wide text-muted">
          page · read-only via Skill
        </div>
        <div className="mt-6">
          <PageBody page={page} />
        </div>
      </div>
    </div>
  );
}
