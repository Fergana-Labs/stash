"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Code2, ExternalLink, Globe, Lock } from "lucide-react";
import Link from "next/link";
import { CardGridSkeleton } from "@/components/SkeletonStates";
import { GitHubIcon } from "@/components/integrations/BrandIcons";
import ForkSkillCardButton from "@/components/skill/ForkSkillCardButton";
import SkillCard from "@/components/skill/SkillCard";
import {
  getHomeFeed,
  githubOwner,
  type FeedItem,
  type PublicPageCard,
  type ResurfaceCardData,
} from "@/lib/api";
import { routes } from "@/lib/workspace-routes";

const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

/** The home feature — one continuous feed: community skills to copy, public
 *  pages, and (signed in) resurfaced items from your own stash. */
export default function HomePage() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [nextCursor, setNextCursor] = useState<number | null>(0);
  const [fetching, setFetching] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const loadMore = useCallback(async () => {
    if (fetching || nextCursor === null) return;
    setFetching(true);
    try {
      const page = await getHomeFeed(nextCursor);
      setItems((prev) => [...prev, ...page.items]);
      setNextCursor(page.next_cursor);
    } finally {
      setFetching(false);
      setInitialLoad(false);
    }
  }, [fetching, nextCursor]);

  useEffect(() => {
    loadMore();
    // Load the first page once on mount; scrolling drives the rest.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore();
      },
      { rootMargin: "600px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore]);

  return (
    <div className="min-h-full">
      {/* Header */}
      <div className="border-b border-border">
        <div className="mx-auto flex max-w-[720px] items-baseline justify-between gap-4 px-6 py-8">
          <h1 className="font-display text-[28px] font-bold leading-[1.05] tracking-[-0.02em] text-foreground">
            Your feed
          </h1>
          <Link
            href="/discover"
            className="shrink-0 text-[13px] font-medium text-brand-600 hover:underline"
          >
            View all collections →
          </Link>
        </div>
      </div>

      {/* Feed */}
      <div className="mx-auto max-w-[720px] px-6 pb-20 pt-6">
        <ExtensionCta />
        {initialLoad ? (
          <CardGridSkeleton className="mt-5" />
        ) : items.length === 0 ? (
          <section className="mt-12 rounded-lg border border-dashed border-border bg-base px-6 py-12 text-center">
            <h2 className="font-display text-[20px] font-bold text-foreground">Nothing here yet.</h2>
            <p className="mx-auto mt-2 max-w-[440px] text-[13.5px] leading-[1.6] text-muted-foreground">
              Community workflows, pages, and your own resurfaced saves will show up here.
            </p>
          </section>
        ) : (
          <div className="mt-5 flex flex-col gap-5">
            {items.map((item, i) => (
              <FeedCard key={feedKey(item, i)} item={item} index={i} />
            ))}
          </div>
        )}
        <div ref={sentinelRef} />
        {fetching && !initialLoad && (
          <div className="py-6 text-center text-[12.5px] text-muted-foreground">Loading…</div>
        )}
      </div>
    </div>
  );
}

function feedKey(item: FeedItem, index: number): string {
  if (item.kind === "skill") return `skill-${item.data.id}`;
  if (item.kind === "public_page") return `page-${item.data.slug}`;
  return `resurface-${index}-${item.data.title}`;
}

function FeedCard({ item, index }: { item: FeedItem; index: number }) {
  return (
    <div>
      <ProvenanceLabel internal={item.kind === "resurface"} />
      <FeedCardBody item={item} index={index} />
    </div>
  );
}

// Every card says where it came from, so the user never has to wonder whether
// they are looking at public community content or their own private data.
function ProvenanceLabel({ internal }: { internal: boolean }) {
  if (internal) {
    return (
      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-brand-600">
        <Lock className="h-3 w-3" />
        From your stash
        <span className="font-normal normal-case tracking-normal text-muted-foreground">
          · only visible to you
        </span>
      </div>
    );
  }
  return (
    <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
      <Globe className="h-3 w-3" />
      From the community
    </div>
  );
}

function FeedCardBody({ item, index }: { item: FeedItem; index: number }) {
  if (item.kind === "skill") {
    const skill = item.data;
    return (
      <SkillCard
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
        cover={COVERS[index % COVERS.length]}
        cornerAction={
          <span className="flex items-center gap-1.5">
            {skill.source_github_url && <GitHubSourceGlyph href={skill.source_github_url} />}
            <ForkSkillCardButton slug={skill.slug} />
          </span>
        }
      />
    );
  }
  if (item.kind === "public_page") return <PageCard page={item.data} />;
  return <ResurfaceCard data={item.data} />;
}

// A card from the user's own stash: the archived content is the preview; a
// clip opens in-app, an X/Instagram save opens the original post.
function ResurfaceCard({ data }: { data: ResurfaceCardData }) {
  const body = (
    <>
      <div className="flex items-center gap-2 text-[11px]">
        <span className="rounded bg-brand-50 px-1.5 py-0.5 font-mono text-[10px] text-brand-600">
          {sourceLabel(data.source)}
        </span>
        <span className="text-muted-foreground">saved {savedAgo(data.saved_at)}</span>
      </div>
      <div className="mt-2 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="line-clamp-2 text-[14.5px] font-semibold leading-snug text-foreground group-hover:text-brand-600">
            {data.title || "Untitled"}
          </div>
          {data.preview && (
            <p className="mt-1 line-clamp-3 text-[13px] leading-[1.55] text-dim">{data.preview}</p>
          )}
        </div>
        {data.image_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={data.image_url}
            alt=""
            className="h-16 w-16 shrink-0 rounded-lg border border-border object-cover"
          />
        )}
      </div>
    </>
  );
  const className =
    "group block rounded-xl border border-brand-200/70 bg-gradient-to-br from-brand-50/60 to-base p-4 transition hover:border-brand-300 hover:shadow-sm";
  if (data.app_url) {
    return (
      <Link href={data.app_url} className={className}>
        {body}
      </Link>
    );
  }
  return (
    <a href={data.external_url ?? "#"} target="_blank" rel="noreferrer" className={className}>
      {body}
      <span className="mt-2 inline-flex items-center gap-1 text-[11.5px] text-muted-foreground">
        <ExternalLink className="h-3 w-3" /> View original
      </span>
    </a>
  );
}

function sourceLabel(source: ResurfaceCardData["source"]): string {
  if (source === "x") return "X";
  if (source === "instagram") return "Instagram";
  if (source === "doc") return "Doc";
  if (source === "file") return "File";
  if (source === "memory") return "Memory";
  return "Clip";
}

function savedAgo(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

function ExtensionCta() {
  return (
    <Link
      href={routes.extension}
      className="group flex items-center justify-between gap-4 rounded-xl border border-brand-300/60 bg-gradient-to-r from-brand-50 to-base px-5 py-4 transition hover:border-brand-400 hover:shadow-sm"
    >
      <div>
        <div className="text-[14.5px] font-semibold text-foreground group-hover:text-brand-600">
          Download the extension
        </div>
        <div className="mt-0.5 text-[12.5px] text-muted-foreground">
          Clip pages, import bookmarks, and sync your Instagram saves and AI chats into Stash.
        </div>
      </div>
      <span className="shrink-0 rounded-full bg-brand px-4 py-1.5 text-[12px] font-semibold text-white">
        Get it →
      </span>
    </Link>
  );
}

// A community page (pastebin) card — opens the in-app viewer at /pages/[slug].
function PageCard({ page }: { page: PublicPageCard }) {
  const Icon = page.content_type === "html" ? Code2 : FileText;
  return (
    <Link
      href={`/pages/${page.slug}`}
      className="group flex items-center gap-3.5 rounded-xl border border-border bg-base p-4 transition hover:border-brand-300 hover:shadow-sm"
    >
      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-surface text-muted-foreground">
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 text-[14.5px] font-semibold leading-snug text-foreground group-hover:text-brand-600">
          {page.title || "Untitled"}
        </span>
        <span className="mt-1 flex items-center gap-2 text-[11.5px] text-muted-foreground">
          <span className="rounded bg-surface px-1.5 py-0.5 font-medium uppercase tracking-wide">
            {page.content_type}
          </span>
          <span>
            {page.view_count} view{page.view_count === 1 ? "" : "s"}
          </span>
        </span>
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
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        window.open(href, "_blank", "noopener");
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          e.stopPropagation();
          window.open(href, "_blank", "noopener");
        }
      }}
      className="inline-flex cursor-pointer items-center rounded-full bg-white/85 p-1 text-foreground shadow-sm ring-1 ring-border backdrop-blur transition hover:bg-white"
    >
      <GitHubIcon size={13} />
    </span>
  );
}
