import Link from "next/link";

import type { CatalogCard } from "../../lib/api";

const BACKEND_ORIGIN =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

type SearchParams = {
  q?: string;
  sort?: "trending" | "newest" | "forks";
  category?: string;
  tag?: string;
};

async function fetchCatalog(params: SearchParams): Promise<{ workspaces: CatalogCard[] }> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) qs.set(k, v);
  const res = await fetch(
    `${BACKEND_ORIGIN}/api/v1/discover/workspaces${qs.size ? `?${qs}` : ""}`,
    { next: { revalidate: 60 } }
  );
  if (!res.ok) return { workspaces: [] };
  return res.json();
}

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const sort = params.sort ?? "trending";
  const { workspaces } = await fetchCatalog({ ...params, sort });

  return (
    <main className="mx-auto max-w-[1200px] px-7 py-12">
      <h1 className="font-display text-[36px] font-black tracking-[-0.03em] text-ink">
        Discover Stashes
      </h1>
      <p className="mt-2 text-[15px] text-dim">
        Public Stashes you can read, fork, or join.
      </p>

      <div className="mt-6 flex flex-wrap gap-2 border-b border-border-subtle pb-2">
        {(["trending", "newest", "forks"] as const).map((key) => (
          <Link
            key={key}
            href={`/discover?sort=${key}${params.q ? `&q=${encodeURIComponent(params.q)}` : ""}`}
            className={`rounded-md px-3 py-2 text-[14px] transition ${
              sort === key ? "bg-raised text-ink" : "text-dim hover:bg-raised hover:text-ink"
            }`}
          >
            {key === "forks" ? "Most forked" : key.charAt(0).toUpperCase() + key.slice(1)}
          </Link>
        ))}
      </div>

      {workspaces.length === 0 ? (
        <p className="mt-12 text-center text-[14px] text-muted">No public Stashes yet.</p>
      ) : (
        <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {workspaces.map((w) => (
            <Card key={w.id} ws={w} />
          ))}
        </div>
      )}
    </main>
  );
}

function Card({ ws }: { ws: CatalogCard }) {
  const owner = ws.creator_display_name || ws.creator_name;
  return (
    <Link
      href={`/s/${ws.id}`}
      className="group flex flex-col rounded-xl border border-border-subtle bg-raised/30 p-5 transition hover:border-ink"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-[18px] font-bold text-ink group-hover:text-brand">
          {ws.name}
        </h3>
        {ws.featured ? (
          <span className="rounded-md border border-brand/40 px-1.5 py-0.5 font-mono text-[10px] uppercase text-brand">
            Featured
          </span>
        ) : null}
      </div>
      <p className="mt-2 line-clamp-2 text-[14px] text-dim">
        {ws.summary || ws.description || "No description yet."}
      </p>
      <p className="mt-3 font-mono text-[11px] uppercase tracking-wider text-muted">
        {ws.notebook_count} notebooks · {ws.table_count} tables · {ws.deck_count} decks
      </p>
      <div className="mt-auto flex items-center justify-between pt-4 text-[12px] text-dim">
        <span>by {owner}</span>
        <span>★ {ws.fork_count}</span>
      </div>
    </Link>
  );
}
