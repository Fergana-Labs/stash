"use client";

import { useEffect, useState, type ReactNode } from "react";
import { FileText, Code2 } from "lucide-react";
import Link from "next/link";
import { CardGridSkeleton } from "@/components/SkeletonStates";
import { GitHubIcon } from "@/components/integrations/BrandIcons";
import ForkSkillCardButton from "@/components/skill/ForkSkillCardButton";
import SkillCard from "@/components/skill/SkillCard";
import { StashIcon } from "@/components/SkillIcons";
import { API_BASE, githubOwner, listPublicPages, type PublicSkillCard, type PublicPageCard } from "@/lib/api";

const SORTS = ["trending", "newest", "popular"] as const;
type Sort = (typeof SORTS)[number];
const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

async function fetchPublicSkills(params: { q?: string; sort: Sort }): Promise<PublicSkillCard[]> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) qs.set(k, v);
  const res = await fetch(`${API_BASE}/api/v1/discover/skills${qs.size ? `?${qs}` : ""}`);
  if (!res.ok) return [];
  return (await res.json()).skills ?? [];
}

/** The home / Discover feature — a dressed hero over the public-Skills catalog. */
export default function HomePage() {
  const [sort, setSort] = useState<Sort>("trending");
  const [query, setQuery] = useState("");
  const [skills, setSkills] = useState<PublicSkillCard[]>([]);
  const [pages, setPages] = useState<PublicPageCard[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    setFetching(true);
    fetchPublicSkills({ q: query || undefined, sort }).then(setSkills).finally(() => setFetching(false));
  }, [query, sort]);

  // Public pages (pastebin) are the same across sorts — fetched once, filtered client-side.
  useEffect(() => { listPublicPages().then(setPages); }, []);
  const q = query.trim().toLowerCase();
  const visiblePages = q ? pages.filter((p) => p.title.toLowerCase().includes(q)) : pages;

  return (
    <div className="min-h-full">
      {/* Hero */}
      <div className="relative overflow-hidden border-b border-border bg-gradient-to-br from-brand-100 via-brand-50 to-[color:var(--bg-surface)]">
        <div className="mx-auto max-w-[1180px] px-12 py-14">
          <div className="flex items-center gap-2 text-brand-600">
            <StashIcon className="text-[26px]" />
            <span className="text-[13px] font-semibold uppercase tracking-[0.14em]">Discover</span>
          </div>
          <h1 className="mt-4 max-w-[680px] font-display text-[40px] font-bold leading-[1.05] tracking-[-0.02em] text-foreground">
            Get a head start with the community.
          </h1>
          <p className="mt-3 max-w-[580px] text-[15px] leading-[1.6] text-dim">
            Explore public workflows, pages, and docs shared by the community — fork anything into your workspace and make it your own.
          </p>
          <div className="mt-6 flex max-w-[520px] items-center gap-2 rounded-full border border-border bg-base px-4 py-2.5 shadow-sm">
            <SearchGlyph />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search the community…"
              className="min-w-0 flex-1 border-0 bg-transparent text-[14px] text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Catalog */}
      <div className="mx-auto max-w-[1180px] px-12 pb-20 pt-8">
        <div className="flex items-center gap-3">
          <div className="inline-flex gap-0.5 rounded-lg border border-border bg-base p-[3px]">
            {SORTS.map((o) => (
              <button
                key={o}
                onClick={() => setSort(o)}
                className={"cursor-pointer rounded-md px-3 py-1 text-[12.5px] " + (sort === o ? "bg-raised font-semibold text-foreground" : "text-muted-foreground hover:text-foreground")}
              >
                {sortLabel(o)}
              </button>
            ))}
          </div>
          <span className="flex-1" />
          <span className="sys-label" style={{ fontSize: 10.5 }}>{skills.length + visiblePages.length} result{skills.length + visiblePages.length === 1 ? "" : "s"}</span>
        </div>

        {fetching ? (
          <CardGridSkeleton className="mt-6" />
        ) : skills.length === 0 && visiblePages.length === 0 ? (
          <section className="mt-12 rounded-lg border border-dashed border-border bg-base px-6 py-12 text-center">
            <h2 className="font-display text-[20px] font-bold text-foreground">Nothing here yet.</h2>
            <p className="mx-auto mt-2 max-w-[440px] text-[13.5px] leading-[1.6] text-muted-foreground">Community workflows, pages, and docs will show up here as people share them publicly.</p>
          </section>
        ) : (
          <>
            {skills.length > 0 && (
              <>
                <SectionHeading>Workflows &amp; skills</SectionHeading>
                <div className="mt-4 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
                  {skills.map((skill, i) => (
                    <SkillCard
                      key={skill.id}
                      href={`/skills/${skill.slug}`}
                      skill={{
                        title: skill.title,
                        description: skill.description,
                        cover_image_url: skill.cover_image_url,
                        owner_name: skill.owner_name,
                        owner_display_name: skill.source_github_url ? githubOwner(skill.source_github_url) : skill.owner_display_name,
                        updated_at: skill.updated_at,
                      }}
                      cover={COVERS[i % COVERS.length]}
                      badge={sort === "trending" && i < 2 ? (
                        <span className="absolute left-3 top-2.5 inline-flex items-center gap-1 rounded-full bg-black/80 px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.04em] text-white">↗ trending</span>
                      ) : undefined}
                      cornerAction={
                        <span className="flex items-center gap-1.5">
                          {skill.source_github_url && <GitHubSourceGlyph href={skill.source_github_url} />}
                          <ForkSkillCardButton slug={skill.slug} />
                        </span>
                      }
                    />
                  ))}
                </div>
              </>
            )}

            {visiblePages.length > 0 && (
              <>
                <SectionHeading className="mt-12">Community pages</SectionHeading>
                <div className="mt-4 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
                  {visiblePages.map((p) => <PageCard key={p.slug} page={p} />)}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function SectionHeading({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <h2 className={`text-[12px] font-semibold uppercase tracking-[0.1em] text-muted-foreground ${className}`}>{children}</h2>;
}

// A community page (pastebin) card — opens the in-app viewer at /pages/[slug].
function PageCard({ page }: { page: PublicPageCard }) {
  const Icon = page.content_type === "html" ? Code2 : FileText;
  return (
    <Link
      href={`/pages/${page.slug}`}
      className="group flex flex-col gap-3 rounded-xl border border-border bg-base p-4 transition hover:border-brand-300 hover:shadow-sm"
    >
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-surface text-muted-foreground">
        <Icon className="h-4 w-4" />
      </span>
      <span className="line-clamp-2 text-[14.5px] font-semibold leading-snug text-foreground group-hover:text-brand-600">{page.title || "Untitled"}</span>
      <span className="mt-auto flex items-center gap-2 text-[11.5px] text-muted-foreground">
        <span className="rounded bg-surface px-1.5 py-0.5 font-medium uppercase tracking-wide">{page.content_type}</span>
        <span>{page.view_count} view{page.view_count === 1 ? "" : "s"}</span>
      </span>
    </Link>
  );
}

function GitHubSourceGlyph({ href }: { href: string }) {
  return (
    <span
      role="link"
      tabIndex={0}
      title="View source on GitHub"
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); window.open(href, "_blank", "noopener"); }}
      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); window.open(href, "_blank", "noopener"); } }}
      className="inline-flex cursor-pointer items-center rounded-full bg-white/85 p-1 text-foreground shadow-sm ring-1 ring-border backdrop-blur transition hover:bg-white"
    >
      <GitHubIcon size={13} />
    </span>
  );
}

function sortLabel(sort: Sort): string {
  return sort === "popular" ? "Most viewed" : sort === "trending" ? "Trending" : "Newest";
}
function SearchGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted-foreground">
      <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
    </svg>
  );
}
