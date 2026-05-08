"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Markdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import AppShell from "../../../../../components/AppShell";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../../hooks/useAuth";
import { getPage, getWorkspace } from "../../../../../lib/api";
import type { Page, Workspace } from "../../../../../lib/types";

export default function StashPageView() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const pageId = params.pageId as string;
  const { user, loading, logout } = useAuth();

  const [stash, setStash] = useState<Workspace | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState("");

  useBreadcrumbs(
    page ? [{ label: page.name.replace(/\.md$/, "") }] : [{ label: "Page" }],
    `${stashId}/page/${pageId}/${page?.name ?? ""}`
  );

  const load = useCallback(async () => {
    try {
      setStash(await getWorkspace(stashId));
      setPage(await getPage(stashId, pageId));
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

  const isNarrative = page?.name?.toLowerCase().startsWith("narrative");
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
        {/* Notion-style hero gradient strip — taller for narratives */}
        <div
          className={
            "w-full " +
            (isNarrative
              ? "h-28 bg-gradient-to-r from-[var(--color-brand-700)] via-[var(--color-brand-500)] to-emerald-300"
              : "h-16 bg-gradient-to-r from-[var(--color-brand-200)] via-[var(--color-brand-100)] to-amber-100")
          }
        />
        <div className="mx-auto -mt-6 max-w-3xl px-12 pb-20">
          <div className="text-5xl">{isNarrative ? "📌" : "📄"}</div>
          <h1 className="mt-1 font-display text-[36px] font-bold tracking-tight text-foreground">
            {(page?.name || "").replace(/\.md$/, "")}
          </h1>
          {updatedAt && (
            <p className="mt-1 text-[12px] text-muted">
              Last edited {updatedAt}
              {stash ? <span> in <span className="text-foreground">{stash.name}</span></span> : null}
            </p>
          )}

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
