"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AppShell from "../../components/AppShell";
import { useBreadcrumbs } from "../../components/BreadcrumbContext";
import { useAuth } from "../../hooks/useAuth";
import type { CatalogCard } from "../../lib/api";

const BACKEND_ORIGIN =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

const SORTS = ["trending", "newest", "forks"] as const;
type Sort = (typeof SORTS)[number];

async function fetchCatalog(params: {
  q?: string;
  sort: Sort;
}): Promise<CatalogCard[]> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) qs.set(key, value);
  }

  const res = await fetch(
    `${BACKEND_ORIGIN}/api/v1/discover/workspaces${qs.size ? `?${qs}` : ""}`,
  );
  if (!res.ok) return [];

  const data = await res.json();
  return data.workspaces ?? [];
}

export default function DiscoverPage() {
  const { user, loading, logout } = useAuth();
  const [sort, setSort] = useState<Sort>("trending");
  const [query, setQuery] = useState("");
  const [stashes, setStashes] = useState<CatalogCard[]>([]);
  const [fetching, setFetching] = useState(true);

  useBreadcrumbs([{ label: "Discover" }], "discover");

  useEffect(() => {
    setFetching(true);
    fetchCatalog({ q: query || undefined, sort })
      .then(setStashes)
      .finally(() => setFetching(false));
  }, [query, sort]);

  const featured = stashes.filter((stash) => stash.featured).slice(0, 3);

  const content = (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <header className="border-b border-border-subtle pb-6">
        <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          Discover
        </p>
        <h1 className="mt-3 font-display text-[34px] font-bold tracking-tight text-foreground">
          Curated public Stashes.
        </h1>
        <p className="mt-2 max-w-[620px] text-[14.5px] leading-[1.6] text-muted">
          Browse high-signal Stashes that owners have made public and the Stash
          team has selected for the catalog.
        </p>
      </header>

      <div className="mt-5 flex flex-col gap-3 lg:flex-row lg:items-center">
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search curated stashes"
          className="min-w-0 flex-1 rounded-lg border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-400)] focus:outline-none"
        />
        <div className="flex rounded-md border border-border bg-base p-0.5 text-[12px]">
          {SORTS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setSort(option)}
              className={
                "rounded px-2.5 py-1 capitalize " +
                (sort === option
                  ? "bg-raised font-medium text-foreground"
                  : "text-muted hover:text-foreground")
              }
            >
              {option === "forks" ? "Most forked" : option}
            </button>
          ))}
        </div>
      </div>

      {fetching ? (
        <p className="mt-12 text-center text-[13px] text-muted">Loading...</p>
      ) : stashes.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          {featured.length > 0 ? <FeaturedShelf stashes={featured} /> : null}
          <section className="mt-8">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-display text-[20px] font-bold text-foreground">
                Public Stashes
              </h2>
              <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
                {stashes.length} result{stashes.length === 1 ? "" : "s"}
              </p>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {stashes.map((stash) => (
                <StashCard key={stash.id} stash={stash} />
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center text-muted">
        Loading...
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

function FeaturedShelf({ stashes }: { stashes: CatalogCard[] }) {
  return (
    <section className="mt-8">
      <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
        Featured
      </p>
      <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {stashes.map((stash) => (
          <StashCard key={stash.id} stash={stash} featured />
        ))}
      </div>
    </section>
  );
}

function StashCard({
  stash,
  featured = false,
}: {
  stash: CatalogCard;
  featured?: boolean;
}) {
  const owner = stash.creator_display_name || stash.creator_name;
  return (
    <Link
      href={`/stashes/${stash.id}`}
      className={
        "group flex min-h-[260px] flex-col overflow-hidden rounded-xl border border-border bg-base transition hover:border-[var(--color-brand-300)] " +
        (featured ? "shadow-[0_14px_38px_rgba(15,23,42,0.08)]" : "")
      }
    >
      <Cover stash={stash} />
      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display text-[17px] font-bold text-foreground group-hover:text-[var(--color-brand-700)]">
            {stash.name}
          </h3>
          {stash.featured ? (
            <span className="shrink-0 rounded-md border border-[var(--color-brand-300)] px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--color-brand-700)]">
              Featured
            </span>
          ) : null}
        </div>
        <p className="mt-2 line-clamp-3 text-[13.5px] leading-[1.55] text-muted">
          {stash.summary || stash.description || "No description."}
        </p>
        <p className="mt-3 font-mono text-[11px] uppercase tracking-wider text-muted">
          {stash.page_count} pages / {stash.table_count} tables /{" "}
          {stash.file_count} files
        </p>
        {stash.tags?.length ? (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {stash.tags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="rounded-md border border-border-subtle bg-raised px-2 py-0.5 font-mono text-[10px] text-muted"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}
        <div className="mt-auto flex items-center justify-between gap-3 pt-4 text-[12px] text-dim">
          <span className="min-w-0 truncate">by {owner}</span>
          <span className="shrink-0">
            {stash.fork_count} fork{stash.fork_count === 1 ? "" : "s"}
          </span>
        </div>
      </div>
    </Link>
  );
}

function Cover({ stash }: { stash: CatalogCard }) {
  if (stash.cover_image_url) {
    return (
      <div
        className="h-28 border-b border-border bg-cover bg-center"
        style={{ backgroundImage: `url(${stash.cover_image_url})` }}
      />
    );
  }

  const hue = hashHue(stash.id);
  return (
    <div
      className="h-28 border-b border-border"
      style={{
        background: `linear-gradient(135deg, hsl(${hue} 58% 64% / 0.95), hsl(${(hue + 42) % 360} 52% 48% / 0.82))`,
      }}
    />
  );
}

function EmptyState() {
  return (
    <section className="mt-12 rounded-lg border border-dashed border-border bg-base px-6 py-12 text-center">
      <h2 className="font-display text-[20px] font-bold text-foreground">
        No curated public Stashes yet.
      </h2>
      <p className="mx-auto mt-2 max-w-[420px] text-[13.5px] leading-[1.6] text-muted">
        Public Stashes appear here after they are selected for Discover.
      </p>
    </section>
  );
}

function hashHue(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash * 31 + id.charCodeAt(i)) & 0xffffffff;
  }
  return Math.abs(hash) % 360;
}
