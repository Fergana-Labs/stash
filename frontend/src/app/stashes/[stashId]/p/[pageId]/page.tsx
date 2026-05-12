"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Markdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import AppShell from "../../../../../components/AppShell";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { PageIcon } from "../../../../../components/StashIcons";
import { useAuth } from "../../../../../hooks/useAuth";
import {
  getFolderContents,
  getPage,
  getWorkspace,
  type FolderBreadcrumb,
} from "../../../../../lib/api";
import type { Page, Workspace } from "../../../../../lib/types";

export default function StashPageView() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const pageId = params.pageId as string;
  const { user, loading, logout } = useAuth();

  const [stash, setStash] = useState<Workspace | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [folderChain, setFolderChain] = useState<FolderBreadcrumb[]>([]);
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
      const [workspace, p] = await Promise.all([
        getWorkspace(stashId),
        getPage(stashId, pageId),
      ]);
      setStash(workspace);
      setPage(p);
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
    <AppShell user={user} onLogout={logout}>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="h-16 w-full bg-gradient-to-r from-[var(--color-brand-200)] via-[var(--color-brand-100)] to-amber-100" />
        <div className="mx-auto -mt-6 max-w-3xl px-12 pb-20">
          <div className="flex h-12 w-12 items-center justify-center text-5xl text-muted">
            <PageIcon />
          </div>
          <h1 className="mt-1 font-display text-[36px] font-bold tracking-tight text-foreground">
            {(page?.name || "").replace(/\.md$/, "")}
          </h1>
          <div className="mt-1 flex items-center gap-3 text-[12px] text-muted">
            {updatedAt && (
              <span>
                Last edited {updatedAt}
                {stash ? <span> in <span className="text-foreground">{stash.name}</span></span> : null}
              </span>
            )}
            {/* "Visible in share" checkbox is gone — sharing is now link-based.
                Use the Share button (workspace toolbar) to mint a share-link
                for this page with target_type='page'. */}
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          <article className="markdown-content mt-8 text-[15px] leading-relaxed text-foreground">
            {page ? (
              <Markdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeRaw]}
              >
                {page.content_markdown || ""}
              </Markdown>
            ) : (
              <p className="text-muted">Loading…</p>
            )}
          </article>
        </div>
      </div>
    </AppShell>
  );
}
