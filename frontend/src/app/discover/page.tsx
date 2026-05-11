import type { Metadata } from "next";
import Link from "next/link";

import type { CatalogCard } from "../../lib/api";

const BACKEND_ORIGIN =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

export const metadata: Metadata = {
  title: "Discover - Stash",
  description: "Browse curated public Stashes from teams building in the open.",
};

type SearchParams = {
  q?: string;
  sort?: string;
  category?: string;
  tag?: string;
  tab?: "workspaces" | "views";
};

interface PublicViewCard {
  id: string;
  slug: string;
  title: string;
  description: string;
  cover_image_url: string | null;
  view_count: number;
  owner_name: string | null;
  owner_display_name: string | null;
  workspace_id: string;
  workspace_name: string | null;
  item_count: number;
  created_at: string;
  updated_at: string;
}

async function fetchCatalog(
  params: SearchParams,
): Promise<{ workspaces: CatalogCard[] }> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries({
    q: params.q,
    sort: params.sort,
    category: params.category,
    tag: params.tag,
  })) {
    if (v) qs.set(k, v);
  }
  const res = await fetch(
    `${BACKEND_ORIGIN}/api/v1/discover/workspaces${qs.size ? `?${qs}` : ""}`,
    { next: { revalidate: 60 } },
  );
  if (!res.ok) return { workspaces: [] };
  return res.json();
}

async function fetchViews(
  params: SearchParams,
): Promise<{ views: PublicViewCard[] }> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.sort) qs.set("sort", params.sort);
  const res = await fetch(
    `${BACKEND_ORIGIN}/api/v1/discover/views${qs.size ? `?${qs}` : ""}`,
    { next: { revalidate: 30 } },
  );
  if (!res.ok) return { views: [] };
  return res.json();
}

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const tab = params.tab ?? "workspaces";
  const isViews = tab === "views";

  const sortOptions = isViews
    ? (["trending", "newest", "popular"] as const)
    : (["trending", "newest", "forks"] as const);
  const sort = (sortOptions as readonly string[]).includes(params.sort ?? "")
    ? (params.sort as string)
    : sortOptions[0];

  const data = isViews
    ? await fetchViews({ ...params, sort })
    : await fetchCatalog({ ...params, sort });

  const workspaces = isViews
    ? []
    : (data as { workspaces: CatalogCard[] }).workspaces;
  const views = isViews ? (data as { views: PublicViewCard[] }).views : [];
  const featured = workspaces.filter((w) => w.featured).slice(0, 3);
  const totalItems = isViews ? views.length : workspaces.length;

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-[1180px] px-6 py-8 sm:px-8 lg:py-12">
        <header className="flex flex-col gap-8 border-b border-border-subtle pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-[720px]">
            <Link
              href="/"
              className="font-display text-[20px] font-black tracking-[-0.03em] text-foreground"
            >
              stash
            </Link>
            <p className="mt-8 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
              Discover
            </p>
            <h1 className="mt-3 font-display text-[clamp(34px,5vw,58px)] font-black leading-[1.02] tracking-[-0.035em] text-foreground">
              Curated public Stashes.
            </h1>
            <p className="mt-4 max-w-[620px] text-[16px] leading-[1.65] text-dim">
              Browse high-signal workspaces that owners have made public and
              the Stash team has selected for the catalog.
            </p>
          </div>

          <div className="grid w-full max-w-[360px] grid-cols-3 gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
            <Stat label="Listed" value={formatNumber(totalItems)} />
            <Stat
              label={isViews ? "Views" : "Featured"}
              value={formatNumber(isViews ? views.length : featured.length)}
            />
            <Stat label="Mode" value={isViews ? "Views" : "Stashes"} />
          </div>
        </header>

        <section className="mt-7">
          <div className="flex flex-col gap-4 border-b border-border-subtle pb-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="flex items-center gap-2">
              {(["workspaces", "views"] as const).map((t) => (
                <Link
                  key={t}
                  href={hrefFor({ ...params, tab: t, sort: undefined })}
                  className={
                    "rounded-md px-3 py-2 text-[14px] transition " +
                    (tab === t
                      ? "bg-raised font-medium text-foreground"
                      : "text-dim hover:bg-raised hover:text-foreground")
                  }
                >
                  {t === "workspaces" ? "Stashes" : "Views"}
                </Link>
              ))}
            </div>

            <form action="/discover" className="flex w-full gap-2 lg:max-w-[520px]">
              <input type="hidden" name="tab" value={tab} />
              <input type="hidden" name="sort" value={sort} />
              {params.category ? (
                <input type="hidden" name="category" value={params.category} />
              ) : null}
              {params.tag ? <input type="hidden" name="tag" value={params.tag} /> : null}
              <input
                name="q"
                defaultValue={params.q ?? ""}
                placeholder={isViews ? "Search views" : "Search stashes"}
                className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-2 text-[14px] text-foreground outline-none transition placeholder:text-muted focus:border-brand"
              />
              <button
                type="submit"
                className="rounded-md bg-foreground px-4 py-2 text-[14px] font-medium text-background transition hover:opacity-90"
              >
                Search
              </button>
            </form>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {sortOptions.map((key) => (
              <Link
                key={key}
                href={hrefFor({ ...params, tab, sort: key })}
                className={`rounded-md px-3 py-1.5 text-[13px] transition ${
                  sort === key
                    ? "bg-raised text-foreground"
                    : "text-dim hover:bg-raised hover:text-foreground"
                }`}
              >
                {sortLabel(key)}
              </Link>
            ))}
            {(params.q || params.category || params.tag) && (
              <Link
                href={hrefFor({ tab, sort })}
                className="rounded-md px-3 py-1.5 text-[13px] text-muted transition hover:bg-raised hover:text-foreground"
              >
                Clear filters
              </Link>
            )}
          </div>
        </section>

        {!isViews && featured.length > 0 ? <FeaturedShelf items={featured} /> : null}

        {isViews ? (
          <ViewsGrid views={views} />
        ) : (
          <WorkspacesGrid workspaces={workspaces} />
        )}
      </div>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface px-3 py-3">
      <div className="text-[18px] font-semibold tracking-normal text-foreground">
        {value}
      </div>
      <div className="mt-1 text-[10px]">{label}</div>
    </div>
  );
}

function FeaturedShelf({ items }: { items: CatalogCard[] }) {
  return (
    <section className="mt-10">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            Featured
          </p>
          <h2 className="mt-1 font-display text-[24px] font-bold tracking-[-0.02em] text-foreground">
            Start here
          </h2>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {items.map((w) => (
          <WorkspaceCard key={w.id} ws={w} prominent />
        ))}
      </div>
    </section>
  );
}

function WorkspacesGrid({ workspaces }: { workspaces: CatalogCard[] }) {
  if (workspaces.length === 0) {
    return (
      <EmptyState
        title="No curated Stashes yet."
        body="Public workspaces appear here after they are selected for Discover."
      />
    );
  }
  return (
    <section className="mt-10">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            Catalog
          </p>
          <h2 className="mt-1 font-display text-[24px] font-bold tracking-[-0.02em] text-foreground">
            Public Stashes
          </h2>
        </div>
        <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
          {workspaces.length} result{workspaces.length === 1 ? "" : "s"}
        </p>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {workspaces.map((w) => (
          <WorkspaceCard key={w.id} ws={w} />
        ))}
      </div>
    </section>
  );
}

function ViewsGrid({ views }: { views: PublicViewCard[] }) {
  if (views.length === 0) {
    return (
      <EmptyState
        title="No public Views yet."
        body="Published bundles will appear here when their items are publicly readable."
      />
    );
  }
  return (
    <section className="mt-10">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            Catalog
          </p>
          <h2 className="mt-1 font-display text-[24px] font-bold tracking-[-0.02em] text-foreground">
            Public Views
          </h2>
        </div>
        <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
          {views.length} result{views.length === 1 ? "" : "s"}
        </p>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {views.map((v) => (
          <ViewCard key={v.id} view={v} />
        ))}
      </div>
    </section>
  );
}

function WorkspaceCard({
  ws,
  prominent = false,
}: {
  ws: CatalogCard;
  prominent?: boolean;
}) {
  const owner = ws.creator_display_name || ws.creator_name;
  const shape = [
    `${ws.page_count} page${ws.page_count === 1 ? "" : "s"}`,
    `${ws.table_count} table${ws.table_count === 1 ? "" : "s"}`,
    `${ws.file_count} file${ws.file_count === 1 ? "" : "s"}`,
  ].join(" / ");

  return (
    <Link
      href={`/s/${ws.id}`}
      className={
        "group flex min-h-[270px] flex-col overflow-hidden rounded-lg border border-border-subtle bg-surface transition hover:border-foreground/40 " +
        (prominent ? "shadow-[0_18px_50px_rgba(15,23,42,0.08)]" : "")
      }
    >
      <Cover ws={ws} />
      <div className="flex flex-1 flex-col p-4">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display text-[18px] font-bold leading-tight tracking-[-0.01em] text-foreground group-hover:text-brand">
            {ws.name}
          </h3>
          {ws.featured ? (
            <span className="shrink-0 rounded-md border border-brand/35 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-brand">
              Featured
            </span>
          ) : null}
        </div>
        <p className="mt-2 line-clamp-3 text-[14px] leading-[1.55] text-dim">
          {ws.summary || ws.description || "No description yet."}
        </p>
        <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.1em] text-muted">
          {shape}
        </p>
        {ws.tags?.length ? (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {ws.tags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="rounded-md border border-border-subtle bg-background px-2 py-0.5 font-mono text-[10px] text-muted"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}
        <div className="mt-auto flex items-center justify-between gap-3 pt-4 text-[12px] text-dim">
          <span className="min-w-0 truncate">by {owner}</span>
          <span className="shrink-0">
            {ws.fork_count} fork{ws.fork_count === 1 ? "" : "s"}
          </span>
        </div>
      </div>
    </Link>
  );
}

function ViewCard({ view }: { view: PublicViewCard }) {
  const owner = view.owner_display_name || view.owner_name || "Unknown";
  return (
    <Link
      href={`/v/${view.slug}`}
      className="group flex min-h-[220px] flex-col rounded-lg border border-border-subtle bg-surface p-4 transition hover:border-foreground/40"
    >
      <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
        {view.workspace_name ?? "Public view"}
      </p>
      <h3 className="mt-3 font-display text-[18px] font-bold leading-tight tracking-[-0.01em] text-foreground group-hover:text-brand">
        {view.title}
      </h3>
      {view.description ? (
        <p className="mt-2 line-clamp-3 text-[14px] leading-[1.55] text-dim">
          {view.description}
        </p>
      ) : null}
      <p className="mt-4 font-mono text-[11px] uppercase tracking-[0.1em] text-muted">
        {view.item_count} item{view.item_count === 1 ? "" : "s"} / updated{" "}
        {relativeTime(view.updated_at)}
      </p>
      <div className="mt-auto flex items-center justify-between gap-3 pt-4 text-[12px] text-dim">
        <span className="min-w-0 truncate">by {owner}</span>
        <span className="shrink-0">
          {view.view_count} view{view.view_count === 1 ? "" : "s"}
        </span>
      </div>
    </Link>
  );
}

function Cover({ ws }: { ws: CatalogCard }) {
  if (ws.cover_image_url) {
    return (
      <div
        className="h-28 w-full bg-cover bg-center"
        style={{ backgroundImage: `url(${ws.cover_image_url})` }}
      />
    );
  }

  const hue = hashHue(ws.id);
  return (
    <div
      className="flex h-28 w-full items-end border-b border-border-subtle p-4"
      style={{
        background: `linear-gradient(135deg, hsl(${hue} 58% 64% / 0.95), hsl(${(hue + 42) % 360} 52% 48% / 0.82))`,
      }}
    >
      <span className="rounded-md bg-white/85 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-slate-700">
        Stash
      </span>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <section className="mt-12 rounded-lg border border-dashed border-border bg-surface px-6 py-12 text-center">
      <h2 className="font-display text-[22px] font-bold tracking-[-0.02em] text-foreground">
        {title}
      </h2>
      <p className="mx-auto mt-2 max-w-[440px] text-[14px] leading-[1.6] text-dim">
        {body}
      </p>
    </section>
  );
}

function hrefFor(params: SearchParams): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) qs.set(key, value);
  }
  return `/discover${qs.size ? `?${qs.toString()}` : ""}`;
}

function sortLabel(key: string): string {
  if (key === "forks") return "Most forked";
  if (key === "popular") return "Most viewed";
  return key.charAt(0).toUpperCase() + key.slice(1);
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}

function hashHue(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) & 0xffffffff;
  }
  return Math.abs(h) % 360;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
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
