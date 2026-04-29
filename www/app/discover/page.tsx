import type { Metadata } from "next";
import Link from "next/link";

import { APP_URL, fetchCatalog, type CatalogCard } from "../../lib/discover";

export const metadata: Metadata = {
  title: "Discover Stashes · Stash",
  description:
    "Browse public Stashes — shared agent memory, notebooks, tables, and chats from teams building in the open.",
};

type SearchParams = {
  q?: string;
  category?: string;
  tag?: string;
  sort?: "trending" | "newest" | "forks";
};

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const sort = params.sort ?? "trending";
  const { workspaces } = await fetchCatalog({ ...params, sort });

  return (
    <main className="min-h-screen bg-background text-foreground">
      <Header />

      <section className="mx-auto max-w-[1200px] px-7 pb-10 pt-16">
        <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
          Discover
        </p>
        <h1 className="mt-5 text-balance font-display text-[clamp(36px,4.6vw,56px)] font-black leading-[1.02] tracking-[-0.035em] text-ink">
          Public Stashes from teams<br />
          <span className="text-brand">building in the open.</span>
        </h1>
        <p className="mt-6 max-w-[640px] text-[17px] leading-[1.6] text-foreground">
          Browse notebooks, tables, files, and chat history from Stashes that
          their owners have shared with the world. Open one to read it without
          signing in. Fork it to make a copy you can edit.
        </p>

        <SortBar current={sort} query={params.q} />
      </section>

      <section className="mx-auto max-w-[1200px] px-7 pb-24">
        {workspaces.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {workspaces.map((w) => (
              <Card key={w.id} ws={w} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-border-subtle bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-7">
        <Link
          href="/"
          className="font-display text-[20px] font-black tracking-[-0.03em] text-ink"
        >
          stash
        </Link>
        <nav className="flex items-center gap-5 text-[14px] text-dim">
          <Link href="/discover" className="text-ink">
            Discover
          </Link>
          <Link href="/docs" className="transition hover:text-ink">
            Docs
          </Link>
          <Link href="/contact-sales" className="transition hover:text-ink">
            Contact sales
          </Link>
          <Link
            href="/login"
            className="hidden h-10 items-center rounded-lg border border-border bg-background px-[18px] text-[14px] font-medium text-ink transition hover:border-ink sm:inline-flex"
          >
            Sign in
          </Link>
        </nav>
      </div>
    </header>
  );
}

function SortBar({ current, query }: { current: string; query?: string }) {
  const tabs = [
    { key: "trending", label: "Trending" },
    { key: "newest", label: "Newest" },
    { key: "forks", label: "Most forked" },
  ];
  return (
    <div className="mt-10 flex flex-wrap items-center gap-2 border-b border-border-subtle pb-2">
      {tabs.map((t) => {
        const active = t.key === current;
        const href = `/discover?sort=${t.key}${query ? `&q=${encodeURIComponent(query)}` : ""}`;
        return (
          <Link
            key={t.key}
            href={href}
            className={`rounded-md px-3 py-2 text-[14px] transition ${
              active ? "bg-raised text-ink" : "text-dim hover:bg-raised hover:text-ink"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </div>
  );
}

function Card({ ws }: { ws: CatalogCard }) {
  const owner = ws.creator_display_name || ws.creator_name;
  const updated = relativeTime(ws.updated_at);
  const shape = [
    ws.notebook_count && `${ws.notebook_count} notebook${ws.notebook_count === 1 ? "" : "s"}`,
    ws.table_count && `${ws.table_count} table${ws.table_count === 1 ? "" : "s"}`,
    ws.file_count && `${ws.file_count} file${ws.file_count === 1 ? "" : "s"}`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Link
      href={`${APP_URL}/s/${ws.id}`}
      className="group flex flex-col rounded-xl border border-border-subtle bg-raised/40 p-5 transition hover:border-ink"
    >
      <Cover ws={ws} />
      <div className="mt-4 flex items-start justify-between gap-3">
        <h3 className="font-display text-[18px] font-bold leading-tight text-ink group-hover:text-brand">
          {ws.name}
        </h3>
        {ws.featured ? (
          <span className="rounded-md border border-brand/40 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-brand">
            Featured
          </span>
        ) : null}
      </div>
      <p className="mt-2 line-clamp-2 text-[14px] leading-[1.5] text-dim">
        {ws.summary || ws.description || "No description yet."}
      </p>
      {shape ? (
        <p className="mt-3 font-mono text-[11px] uppercase tracking-wider text-muted">
          {shape}
        </p>
      ) : null}
      <div className="mt-auto flex items-center justify-between pt-4 text-[12px] text-dim">
        <span>by {owner}</span>
        <span className="flex items-center gap-3">
          <span title="Forks">★ {ws.fork_count}</span>
          <span title="Members">{ws.member_count} member{ws.member_count === 1 ? "" : "s"}</span>
          <span>{updated}</span>
        </span>
      </div>
      {ws.tags?.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {ws.tags.slice(0, 3).map((t) => (
            <span
              key={t}
              className="rounded-md border border-border-subtle px-2 py-0.5 font-mono text-[10px] text-muted"
            >
              {t}
            </span>
          ))}
        </div>
      ) : null}
    </Link>
  );
}

function Cover({ ws }: { ws: CatalogCard }) {
  if (ws.cover_image_url) {
    return (
      <div
        className="h-28 w-full rounded-lg bg-cover bg-center"
        style={{ backgroundImage: `url(${ws.cover_image_url})` }}
      />
    );
  }
  // Deterministic gradient seeded by id so cards stay stable across renders.
  const hue = hashHue(ws.id);
  const bg = `linear-gradient(135deg, hsl(${hue} 70% 60% / 0.9), hsl(${(hue + 60) % 360} 70% 50% / 0.7))`;
  return <div className="h-28 w-full rounded-lg" style={{ background: bg }} />;
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-border-subtle bg-raised/30 p-12 text-center">
      <p className="font-display text-[20px] font-bold text-ink">
        No public Stashes yet.
      </p>
      <p className="mt-2 text-[14px] text-dim">
        Be the first — flip <code className="font-mono text-brand">is_public</code>{" "}
        on a Stash you own and it will appear here.
      </p>
    </div>
  );
}

function hashHue(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) & 0xffffffff;
  }
  return Math.abs(h) % 360;
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 30) return `${d}d ago`;
  const mo = Math.round(d / 30);
  if (mo < 12) return `${mo}mo ago`;
  return `${Math.round(mo / 12)}y ago`;
}
