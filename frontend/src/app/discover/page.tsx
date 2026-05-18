"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AppShell from "../../components/AppShell";
import { useBreadcrumbs } from "../../components/BreadcrumbContext";
import { useAuth } from "../../hooks/useAuth";
import type { PublicStashCard } from "../../lib/api";

const BACKEND_ORIGIN =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

const SORTS = ["trending", "newest", "popular"] as const;
type Sort = (typeof SORTS)[number];

const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

const TOPICS = [
  "agents infra",
  "design systems",
  "evals",
  "MCP",
  "PRDs",
  "launches",
  "PMing with agents",
  "cursor",
  "eng / runtimes",
];

async function fetchPublicStashes(params: {
  q?: string;
  sort: Sort;
}): Promise<PublicStashCard[]> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) qs.set(key, value);
  }
  const res = await fetch(
    `${BACKEND_ORIGIN}/api/v1/discover/stashes${qs.size ? `?${qs}` : ""}`,
  );
  if (!res.ok) return [];
  const data = await res.json();
  return data.stashes ?? [];
}

export default function DiscoverPage() {
  const { user, loading, logout } = useAuth();
  const [sort, setSort] = useState<Sort>("trending");
  const [query, setQuery] = useState("");
  const [stashes, setStashes] = useState<PublicStashCard[]>([]);
  const [fetching, setFetching] = useState(true);
  const [activeTopic, setActiveTopic] = useState(0);

  useBreadcrumbs([{ label: "Discover" }], "discover");

  useEffect(() => {
    setFetching(true);
    fetchPublicStashes({ q: query || undefined, sort })
      .then(setStashes)
      .finally(() => setFetching(false));
  }, [query, sort]);

  const content = (
    <div className="mx-auto max-w-[1180px] px-12 pb-20 pt-9">
      {/* Hero */}
      <div className="border-b border-border-subtle pb-5">
        <p className="sys-label">Discover</p>
        <h1 className="my-2 font-display text-[44px] font-black leading-[1.05] tracking-[-0.025em]">
          Public Stashes, in the wild.
        </h1>
        <p className="m-0 max-w-[720px] text-[14.5px] leading-[1.55] text-dim">
          Browse Stashes that workspaces have published and shared to Discover.
          Open any of them, fork into your workspace, and it becomes an external
          Stash you and your agents can search.
        </p>
      </div>

      {/* Controls */}
      <div className="mt-4 flex items-center gap-3">
        <div className="flex max-w-[460px] flex-1 items-center gap-2 rounded-lg border border-border bg-base px-2.5 py-1.5">
          <SearchGlyph />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search public Stashes…"
            className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-foreground placeholder:text-muted focus:outline-none"
          />
        </div>
        <div className="inline-flex gap-0.5 rounded-lg border border-border bg-base p-[3px]">
          {SORTS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setSort(option)}
              className={
                "rounded-md px-2.5 py-[3px] text-[12px] " +
                (sort === option
                  ? "bg-raised font-semibold text-foreground"
                  : "text-muted hover:text-foreground")
              }
            >
              {sortLabel(option)}
            </button>
          ))}
        </div>
        <span className="flex-1" />
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {stashes.length} result{stashes.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* Topic chips */}
      <div className="mt-3.5 flex flex-wrap gap-1.5">
        {TOPICS.map((t, i) => {
          const active = i === activeTopic;
          return (
            <button
              key={t}
              type="button"
              onClick={() => setActiveTopic(i)}
              className={
                "rounded-full border px-2.5 py-[3px] text-[11.5px] " +
                (active
                  ? "border-[var(--color-brand-200)] bg-[var(--color-brand-50)] text-[var(--color-brand-700)]"
                  : "border-border bg-transparent text-dim hover:bg-raised")
              }
            >
              {t}
            </button>
          );
        })}
      </div>

      {fetching ? (
        <p className="mt-12 text-center text-[13px] text-muted">Loading…</p>
      ) : stashes.length === 0 ? (
        <EmptyState />
      ) : (
        <DiscoverGrid stashes={stashes} sort={sort} />
      )}
    </div>
  );

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center text-muted">
        Loading…
      </div>
    );
  }

  if (user) {
    return (
      <AppShell user={user} onLogout={logout}>
        {content}
      </AppShell>
    );
  }

  return <main>{content}</main>;
}

function DiscoverGrid({
  stashes,
  sort,
}: {
  stashes: PublicStashCard[];
  sort: Sort;
}) {
  return (
    <div className="mt-6 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
      {stashes.map((stash, i) => (
        <DiscoverStashCard
          key={stash.id}
          stash={stash}
          cover={COVERS[i % COVERS.length]}
          trending={sort === "trending" && i < 2}
        />
      ))}
    </div>
  );
}

function DiscoverStashCard({
  stash,
  cover,
  trending,
}: {
  stash: PublicStashCard;
  cover: string;
  trending: boolean;
}) {
  const owner = stash.owner_display_name || stash.owner_name;
  return (
    <Link
      href={`/stashes/${stash.slug}`}
      className="card group flex min-h-[280px] flex-col overflow-hidden transition hover:border-[var(--color-brand-300)]"
    >
      <div className={`${cover} relative h-24`}>
        {trending && (
          <span
            className="absolute left-3 top-2.5 inline-flex items-center gap-1 rounded-full bg-black/80 px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.04em] text-white"
            style={{ letterSpacing: "0.04em" }}
          >
            ↗ trending
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col p-4">
        <h3 className="m-0 font-display text-[17px] font-bold leading-tight tracking-[-0.015em] group-hover:text-[var(--color-brand-700)]">
          {stash.title}
        </h3>
        <p className="mt-2 line-clamp-3 text-[12.5px] leading-[1.55] text-dim">
          {stash.description || "No description."}
        </p>
        <div className="sys-label mt-3" style={{ fontSize: 10.5 }}>
          {stash.item_count} item{stash.item_count === 1 ? "" : "s"} ·{" "}
          {stash.view_count} view{stash.view_count === 1 ? "" : "s"}
        </div>
        <div className="flex-1" />
        <div className="mt-3.5 flex items-center justify-between gap-1.5 border-t border-border-subtle pt-2.5 text-[11.5px] text-muted">
          <span className="min-w-0 truncate">
            {owner}
            {stash.workspace_name && (
              <>
                {" · "}
                <span className="font-mono text-dim">{stash.workspace_name}</span>
              </>
            )}
          </span>
          <span className="inline-flex flex-shrink-0 items-center gap-1 rounded-md border border-border bg-base px-2 py-0.5 text-[11.5px] font-medium text-foreground group-hover:border-[var(--color-brand-300)] group-hover:bg-[var(--color-brand-50)] group-hover:text-[var(--color-brand-700)]">
            Open →
          </span>
        </div>
      </div>
    </Link>
  );
}

function EmptyState() {
  return (
    <section className="mt-12 rounded-lg border border-dashed border-border bg-base px-6 py-12 text-center">
      <h2 className="font-display text-[20px] font-bold text-foreground">
        No public Stashes yet.
      </h2>
      <p className="mx-auto mt-2 max-w-[420px] text-[13.5px] leading-[1.6] text-muted">
        Public Stashes appear here after their contents are readable from a public link.
      </p>
    </section>
  );
}

function sortLabel(sort: Sort): string {
  if (sort === "popular") return "Most viewed";
  if (sort === "trending") return "Trending";
  return "Newest";
}

function SearchGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}
