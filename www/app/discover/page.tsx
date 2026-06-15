import type { Metadata } from "next";
import Link from "next/link";

import { APP_URL, fetchCatalog, type PublicSkillCard } from "../../lib/discover";

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
  const { skills } = await fetchCatalog({ ...params, sort });

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
        {skills.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {skills.map((skill) => (
              <Card key={skill.id} skill={skill} />
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

function Card({ skill }: { skill: PublicSkillCard }) {
  // GitHub-imported skills credit the repo owner, not the curator account.
  const owner = skill.source_github_url
    ? skill.source_github_url.replace("https://github.com/", "").split("/")[0]
    : skill.owner_display_name || skill.owner_name;
  const updated = relativeTime(skill.updated_at);

  // The whole card is clickable via a stretched link; the GitHub source
  // anchor sits above it (z-10) since anchors can't nest.
  return (
    <div className="group relative flex flex-col rounded-xl border border-border-subtle bg-raised/40 p-5 transition hover:border-ink">
      <Link
        href={`${APP_URL}/skills/${skill.slug}`}
        className="absolute inset-0 rounded-xl"
        aria-label={skill.title}
      />
      <Cover skill={skill} />
      <div className="mt-4 flex items-start justify-between gap-3">
        <h3 className="font-display text-[18px] font-bold leading-tight text-ink group-hover:text-brand">
          {skill.title}
        </h3>
      </div>
      <p className="mt-2 line-clamp-2 text-[14px] leading-[1.5] text-dim">
        {skill.description || "No description yet."}
      </p>
      <div className="mt-auto flex items-center justify-between pt-4 text-[12px] text-dim">
        <span className="flex items-center gap-2">
          by {owner}
          {skill.source_github_url && <GitHubSourceLink href={skill.source_github_url} />}
        </span>
        <span>{updated}</span>
      </div>
    </div>
  );
}

function GitHubSourceLink({ href }: { href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label="View source on GitHub"
      className="relative z-10 inline-flex text-muted transition hover:text-ink"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
        <path d="M12 .5C5.65.5.5 5.65.5 12a11.5 11.5 0 0 0 7.86 10.92c.57.11.78-.25.78-.55v-1.94c-3.2.7-3.87-1.54-3.87-1.54-.52-1.33-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.47.11-3.07 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.21-1.49 3.18-1.18 3.18-1.18.63 1.6.23 2.78.12 3.07.74.81 1.19 1.84 1.19 3.1 0 4.41-2.69 5.38-5.26 5.67.41.35.77 1.05.77 2.12v3.14c0 .3.21.67.79.55A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
      </svg>
    </a>
  );
}

function Cover({ skill }: { skill: PublicSkillCard }) {
  if (skill.cover_image_url) {
    return (
      <div
        className="h-28 w-full rounded-lg bg-cover bg-center"
        style={{ backgroundImage: `url(${skill.cover_image_url})` }}
      />
    );
  }
  const hue = hashHue(skill.id);
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
