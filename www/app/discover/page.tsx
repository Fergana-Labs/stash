import type { Metadata } from "next";
import Link from "next/link";

import { APP_URL, fetchCatalog, type PublicStashCard } from "../../lib/discover";

export const metadata: Metadata = {
  title: "Discover Skills · Stash",
  description:
    "Browse public Skills — shared sessions, pages, tables, and files from teams building in the open.",
};

type SearchParams = {
  q?: string;
  sort?: "trending" | "newest" | "popular";
};

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const sort = params.sort ?? "trending";
  const { stashes } = await fetchCatalog({ ...params, sort });

  return (
    <main className="min-h-screen bg-background text-foreground">
      <Header />

      <section className="mx-auto max-w-[1200px] px-7 pb-10 pt-16">
        <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
          Discover
        </p>
        <h1 className="mt-5 text-balance font-display text-[clamp(36px,4.6vw,56px)] font-black leading-[1.02] tracking-[-0.035em] text-ink">
          Public Skills from teams<br />
          <span className="text-brand">building in the open.</span>
        </h1>
        <p className="mt-6 max-w-[640px] text-[17px] leading-[1.6] text-foreground">
          Browse sessions, pages, tables, and files from public Product
          Skills. Open one to read it without signing in.
        </p>

        <SortBar current={sort} query={params.q} />
      </section>

      <section className="mx-auto max-w-[1200px] px-7 pb-24">
        {stashes.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {stashes.map((stash) => (
              <Card key={stash.id} stash={stash} />
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
    { key: "popular", label: "Most viewed" },
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

function Card({ stash }: { stash: PublicStashCard }) {
  const owner = stash.owner_display_name || stash.owner_name;
  const updated = relativeTime(stash.updated_at);

  return (
    <Link
      href={`${APP_URL}/skills/${stash.slug}`}
      className="group flex flex-col rounded-xl border border-border-subtle bg-raised/40 p-5 transition hover:border-ink"
    >
      <Cover stash={stash} />
      <div className="mt-4 flex items-start justify-between gap-3">
        <h3 className="font-display text-[18px] font-bold leading-tight text-ink group-hover:text-brand">
          {stash.title}
        </h3>
      </div>
      <p className="mt-2 line-clamp-2 text-[14px] leading-[1.5] text-dim">
        {stash.description || "No description yet."}
      </p>
      <p className="mt-3 font-mono text-[11px] uppercase tracking-wider text-muted">
        {stash.item_count} item{stash.item_count === 1 ? "" : "s"} /{" "}
        {stash.view_count} view{stash.view_count === 1 ? "" : "s"}
      </p>
      <div className="mt-auto flex items-center justify-between pt-4 text-[12px] text-dim">
        <span>by {owner}</span>
        <span className="flex items-center gap-3">
          <span>{stash.workspace_name}</span>
          <span>{updated}</span>
        </span>
      </div>
    </Link>
  );
}

function Cover({ stash }: { stash: PublicStashCard }) {
  if (stash.cover_image_url) {
    return (
      <div
        className="h-28 w-full rounded-lg bg-cover bg-center"
        style={{ backgroundImage: `url(${stash.cover_image_url})` }}
      />
    );
  }
  const hue = hashHue(stash.id);
  const bg = `linear-gradient(135deg, hsl(${hue} 70% 60% / 0.9), hsl(${(hue + 60) % 360} 70% 50% / 0.7))`;
  return <div className="h-28 w-full rounded-lg" style={{ background: bg }} />;
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-border-subtle bg-raised/30 p-12 text-center">
      <p className="font-display text-[20px] font-bold text-ink">
        No public Skills yet.
      </p>
      <p className="mt-2 text-[14px] text-dim">
        Public Skills appear here after they are selected for Discover.
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
