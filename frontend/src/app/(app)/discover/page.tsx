"use client";

import { useEffect, useState } from "react";

import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { CardGridSkeleton } from "@/components/SkeletonStates";
import { GitHubIcon } from "@/components/integrations/BrandIcons";
import ForkSkillCardButton from "@/components/skill/ForkSkillCardButton";
import SkillCard from "@/components/skill/SkillCard";
import { API_BASE, githubOwner, type PublicSkillCard } from "@/lib/api";

const SORTS = ["trending", "newest", "popular"] as const;
type Sort = (typeof SORTS)[number];

const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

async function fetchPublicSkills(params: {
  q?: string;
  sort: Sort;
}): Promise<PublicSkillCard[]> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) qs.set(key, value);
  }
  const res = await fetch(
    `${API_BASE}/api/v1/discover/skills${qs.size ? `?${qs}` : ""}`,
  );
  if (!res.ok) return [];
  const data = await res.json();
  return data.skills ?? [];
}

export default function DiscoverPage() {
  const [sort, setSort] = useState<Sort>("trending");
  const [query, setQuery] = useState("");
  const [skills, setSkills] = useState<PublicSkillCard[]>([]);
  const [fetching, setFetching] = useState(true);

  useBreadcrumbs([{ label: "Discover" }], "discover");

  useEffect(() => {
    setFetching(true);
    fetchPublicSkills({ q: query || undefined, sort })
      .then(setSkills)
      .finally(() => setFetching(false));
  }, [query, sort]);

  return (
    <div className="mx-auto max-w-[1180px] px-12 pb-20 pt-9">
      <div className="flex items-center gap-3">
        <div className="flex max-w-[460px] flex-1 items-center gap-2 rounded-lg border border-border bg-base px-2.5 py-1.5">
          <SearchGlyph />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search public Skills…"
            className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
        </div>
        <div className="inline-flex gap-0.5 rounded-lg border border-border bg-base p-[3px]">
          {SORTS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setSort(option)}
              className={
                "cursor-pointer rounded-md px-2.5 py-[3px] text-[12px] " +
                (sort === option
                  ? "bg-raised font-semibold text-foreground"
                  : "text-muted-foreground hover:text-foreground")
              }
            >
              {sortLabel(option)}
            </button>
          ))}
        </div>
        <span className="flex-1" />
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {skills.length} result{skills.length === 1 ? "" : "s"}
        </span>
      </div>

      {fetching ? (
        <CardGridLoading />
      ) : skills.length === 0 ? (
        <EmptyState />
      ) : (
        <DiscoverGrid skills={skills} sort={sort} />
      )}
    </div>
  );
}

function CardGridLoading() {
  return <CardGridSkeleton className="mt-6" />;
}

function DiscoverGrid({
  skills,
  sort,
}: {
  skills: PublicSkillCard[];
  sort: Sort;
}) {
  return (
    <div className="mt-6 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
      {skills.map((skill, i) => {
        const trending = sort === "trending" && i < 2;
        return (
          <SkillCard
            key={skill.id}
            href={`/skills/${skill.slug}`}
            skill={{
              title: skill.title,
              description: skill.description,
              cover_image_url: skill.cover_image_url,
              owner_name: skill.owner_name,
              owner_display_name: skill.source_github_url
                ? githubOwner(skill.source_github_url)
                : skill.owner_display_name,
              updated_at: skill.updated_at,
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
              <span className="flex items-center gap-1.5">
                {skill.source_github_url && (
                  <GitHubSourceGlyph href={skill.source_github_url} />
                )}
                <ForkSkillCardButton slug={skill.slug} />
              </span>
            }
          />
        );
      })}
    </div>
  );
}

// The card is one big link, so this opens GitHub itself instead of nesting an
// anchor (which breaks SSR HTML parsing) — same convention as the fork button.
function GitHubSourceGlyph({ href }: { href: string }) {
  return (
    <span
      role="link"
      tabIndex={0}
      title="View source on GitHub"
      aria-label="View source on GitHub"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        window.open(href, "_blank", "noopener");
      }}
      onKeyDown={(e) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        e.stopPropagation();
        window.open(href, "_blank", "noopener");
      }}
      className="inline-flex cursor-pointer items-center rounded-full bg-white/85 p-1 text-foreground shadow-sm ring-1 ring-border backdrop-blur transition hover:bg-white"
    >
      <GitHubIcon size={13} />
    </span>
  );
}

function EmptyState() {
  return (
    <section className="mt-12 rounded-lg border border-dashed border-border bg-base px-6 py-12 text-center">
      <h2 className="font-display text-[20px] font-bold text-foreground">
        No public Skills yet.
      </h2>
      <p className="mx-auto mt-2 max-w-[420px] text-[13.5px] leading-[1.6] text-muted-foreground">
        Public Skills appear here after their contents are readable from a public link.
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
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted-foreground">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}
