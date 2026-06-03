"use client";

import { useEffect, useState } from "react";

import AppShell from "../../components/AppShell";
import { useBreadcrumbs } from "../../components/BreadcrumbContext";
import { BasicPageSkeleton, CardGridSkeleton } from "../../components/SkeletonStates";
import ForkCartridgeCardButton from "../../components/cartridge/ForkCartridgeCardButton";
import CartridgeCard from "../../components/cartridge/CartridgeCard";
import { useAuth } from "../../hooks/useAuth";
import { API_BASE, type PublicCartridgeCard } from "../../lib/api";

const SORTS = ["trending", "newest", "popular"] as const;
type Sort = (typeof SORTS)[number];

const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

async function fetchPublicStashes(params: {
  q?: string;
  sort: Sort;
}): Promise<PublicCartridgeCard[]> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) qs.set(key, value);
  }
  const res = await fetch(
    `${API_BASE}/api/v1/discover/cartridges${qs.size ? `?${qs}` : ""}`,
  );
  if (!res.ok) return [];
  const data = await res.json();
  return data.cartridges ?? [];
}

export default function DiscoverPage() {
  const { user, loading, logout } = useAuth();
  const [sort, setSort] = useState<Sort>("trending");
  const [query, setQuery] = useState("");
  const [cartridges, setStashes] = useState<PublicCartridgeCard[]>([]);
  const [fetching, setFetching] = useState(true);

  useBreadcrumbs([{ label: "Discover" }], "discover");

  useEffect(() => {
    setFetching(true);
    fetchPublicStashes({ q: query || undefined, sort })
      .then(setStashes)
      .finally(() => setFetching(false));
  }, [query, sort]);

  const content = (
    <div className="mx-auto max-w-[1180px] px-12 pb-20 pt-9">
      <div className="flex items-center gap-3">
        <div className="flex max-w-[460px] flex-1 items-center gap-2 rounded-lg border border-border bg-base px-2.5 py-1.5">
          <SearchGlyph />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search public Cartridges…"
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
          {cartridges.length} result{cartridges.length === 1 ? "" : "s"}
        </span>
      </div>

      {fetching ? (
        <CardGridLoading />
      ) : cartridges.length === 0 ? (
        <EmptyState />
      ) : (
        <DiscoverGrid cartridges={cartridges} sort={sort} />
      )}
    </div>
  );

  if (loading) {
    return <BasicPageSkeleton />;
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

function CardGridLoading() {
  return <CardGridSkeleton className="mt-6" />;
}

function DiscoverGrid({
  cartridges,
  sort,
}: {
  cartridges: PublicCartridgeCard[];
  sort: Sort;
}) {
  return (
    <div className="mt-6 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
      {cartridges.map((stash, i) => {
        const owner = stash.owner_display_name;
        const trending = sort === "trending" && i < 2;
        return (
          <CartridgeCard
            key={stash.id}
            stash={{
              id: stash.id,
              slug: stash.slug,
              title: stash.title,
              description: stash.description,
              cover_image_url: stash.cover_image_url,
              access: "public",
              item_count: stash.item_count,
              updated_at: stash.updated_at,
            }}
            cover={COVERS[i % COVERS.length]}
            badge={
              trending ? (
                <span
                  className="absolute left-3 top-2.5 inline-flex items-center gap-1 rounded-full bg-black/80 px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.04em] text-white"
                  style={{ letterSpacing: "0.04em" }}
                >
                  ↗ trending
                </span>
              ) : undefined
            }
            cornerAction={
              <ForkCartridgeCardButton
                slug={stash.slug}
                sourceWorkspaceId={stash.workspace_id}
              />
            }
            footer={
              <>
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
              </>
            }
          />
        );
      })}
    </div>
  );
}

function EmptyState() {
  return (
    <section className="mt-12 rounded-lg border border-dashed border-border bg-base px-6 py-12 text-center">
      <h2 className="font-display text-[20px] font-bold text-foreground">
        No public Cartridges yet.
      </h2>
      <p className="mx-auto mt-2 max-w-[420px] text-[13.5px] leading-[1.6] text-muted">
        Public Cartridges appear here after their contents are readable from a public link.
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
