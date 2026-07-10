"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ActivitySkeleton, SkeletonBlock } from "@/components/SkeletonStates";
import {
  FileIcon,
  PageIcon,
  SessionsIcon,
  SkillIcon,
} from "@/components/SkillIcons";
import ContributorActivityTimeline from "@/components/viz/ContributorActivityTimeline";
import EmbeddingSpaceExplorer from "@/components/viz/EmbeddingSpaceExplorer";
import WikiGraph from "@/components/memory/WikiGraph";
import {
  getActivityTimeline,
  getEmbeddingProjection,
  getMemoryGraph,
  getMeOverview,
  listActivity,
  type ActivityEvent,
  type MeOverview,
  type WikiGraph as WikiGraphData,
} from "@/lib/api";
import type { ActivityTimeline, EmbeddingProjection } from "@/lib/types";

const PAGE_SIZE = 50;

const AVATAR_CLASSES = [
  "av-rose",
  "av-orange",
  "av-emerald",
  "av-amber",
  "av-sky",
  "av-teal",
  "av-lime",
];

function avatarClassFor(name: string): string {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return AVATAR_CLASSES[h % AVATAR_CLASSES.length];
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} d ago`;
  return new Date(iso).toLocaleDateString();
}

/** The brain dashboard — knowledge map, vitals, commit timeline, and the
 *  recent-learnings feed. Renders as the Memory section's landing content;
 *  the shell guarantees a signed-in user. Scrolls itself (h-full). */
export default function BrainDashboard() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [fetching, setFetching] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [timeline, setTimeline] = useState<ActivityTimeline | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);
  const [overview, setOverview] = useState<MeOverview | null>(null);
  const [graph, setGraph] = useState<WikiGraphData | null>(null);
  const [insightsLoaded, setInsightsLoaded] = useState(false);
  // Captured once so the "last 24h" window doesn't drift across re-renders.
  const [nowMs] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    listActivity({ limit: PAGE_SIZE })
      .then((feed) => {
        if (cancelled) return;
        setEvents(feed.events);
        setHasMore(feed.has_more);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setFetching(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore || events.length === 0) return;
    setLoadingMore(true);
    try {
      const feed = await listActivity({
        limit: PAGE_SIZE,
        before: events[events.length - 1].ts,
      });
      setEvents((prev) => [...prev, ...feed.events]);
      setHasMore(feed.has_more);
    } finally {
      setLoadingMore(false);
    }
  }, [events, hasMore, loadingMore]);

  useEffect(() => {
    if (!sentinelRef.current) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) loadMore();
      },
      { rootMargin: "200px" }
    );
    obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [loadMore]);

  // The brain's vitals + visualizations. All span the user's own content plus
  // everything shared with them (the /me/* aggregates, called without a
  // scope, include readable shared rows).
  useEffect(() => {
    let cancelled = false;
    setInsightsLoaded(false);
    Promise.allSettled([
      getActivityTimeline(30, "day"),
      getEmbeddingProjection(500),
      getMeOverview(),
      getMemoryGraph(),
    ])
      .then(([t, p, o, g]) => {
        if (cancelled) return;
        if (t.status === "fulfilled") setTimeline(t.value);
        if (p.status === "fulfilled") setProjection(p.value);
        if (o.status === "fulfilled") setOverview(o.value);
        if (g.status === "fulfilled") setGraph(g.value);
        setInsightsLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const recent24h = useMemo(() => {
    const since = nowMs - 24 * 60 * 60 * 1000;
    return events.filter((e) => new Date(e.ts).getTime() >= since).length;
  }, [events, nowMs]);

  const knowledgePoints = projection?.stats.total_embeddings ?? 0;

  if (fetching) {
    return (
      <div className="h-full min-h-0 overflow-y-auto">
        <ActivitySkeleton />
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-[1360px] px-8 pb-10 pt-7">
        {/* Header — what this brain holds and how fresh it is. */}
        <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
          Your brain
        </h1>
        <p className="mt-1 text-[13.5px] text-muted-foreground">
          {`${knowledgePoints.toLocaleString()} things learned across your own and shared knowledge · ${recent24h} new in the last 24 hours.`}
        </p>

        {/* Dashboard grid: wiki graph + map/vitals/timeline on the left,
            learnings feed as its own scrolling panel on the right. */}
        <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
            {/* Wiki graph — the curated context graph of linked pages, obsidian
                style. The centerpiece: click a node to open its page. */}
            <VizCard
              label={
                graph
                  ? `Memory wiki · ${graph.nodes.length} pages · ${graph.edges.length} links`
                  : "Memory wiki"
              }
            >
              {!insightsLoaded ? (
                <SkeletonBlock className="h-[360px] w-full" />
              ) : graph && graph.nodes.length > 0 ? (
                <WikiGraph data={graph} />
              ) : (
                <div className="flex h-[360px] items-center justify-center px-2 text-center text-[12.5px] text-muted-foreground">
                  No wiki pages yet. Hit &quot;Curate wiki&quot; in the explorer and the
                  agent will compile your history into a context graph of linked pages.
                </div>
              )}
            </VizCard>

            {/* Vitals — the brain's current size and pulse. */}
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
              <VitalCard label="Knowledge points" value={knowledgePoints} tint="var(--color-brand-600)" />
              <VitalCard label="Pages" value={overview?.pages ?? 0} tint="var(--color-human)" />
              <VitalCard label="Files" value={overview?.files ?? 0} tint="#16A34A" />
              <VitalCard label="Sessions" value={overview?.sessions ?? 0} tint="var(--color-agent)" />
              <VitalCard label="Learned today" value={recent24h} tint="var(--text-muted)" />
            </div>

            {/* Human / agent commits over time. (Decorative.) */}
            <VizCard label="Human / agent commits — last 30 days" scroll>
              {!insightsLoaded ? (
                <SkeletonBlock className="h-40 w-full" />
              ) : timeline && timeline.contributors.length > 0 ? (
                <ContributorActivityTimeline data={timeline} />
              ) : (
                <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">
                  No agent session commits yet. Push a transcript to populate this view.
                </div>
              )}
            </VizCard>
          </div>

          <div className="flex min-h-0 min-w-0 flex-col gap-4">
            {/* Brain map — the knowledge the brain holds, laid out in space. (Decorative.) */}
            <VizCard label="Knowledge map">
              {!insightsLoaded ? (
                <SkeletonBlock className="h-[240px] w-full" />
              ) : projection && projection.points.length > 0 ? (
                <div className="h-[240px]">
                  <EmbeddingSpaceExplorer data={projection} />
                </div>
              ) : (
                <div className="flex h-[240px] items-center justify-center px-2 text-center text-[12.5px] text-muted-foreground">
                  No embeddings indexed yet. Pages, table rows, and session events
                  get embedded as they&apos;re added.
                </div>
              )}
            </VizCard>

            {/* Newsfeed — what the brain has been learning lately. Scrolls in
                place (hard cap — inside a grid, flex-1 can't bound it) so the
                panel row stays a dashboard, not a page. */}
            <section className="flex flex-col">
              <div className="sys-label mb-1.5">Recent learnings</div>
              <div className="card-soft max-h-[480px] overflow-y-auto p-3">
                <div className="flex flex-col gap-2.5">
                  {events.length === 0 ? (
                    <div className="rounded-[10px] border border-border bg-base px-4 py-6 text-center text-[13px] text-muted-foreground">
                      Nothing learned yet. Push a transcript, edit a page, or
                      upload a file.
                    </div>
                  ) : (
                    events.map((event, i) => (
                      <FeedCard
                        key={`${event.kind}-${event.target_id}-${i}`}
                        event={event}
                      />
                    ))
                  )}
                  {loadingMore && (
                    <div className="py-2 text-center text-[12.5px] text-muted-foreground">
                      Loading more…
                    </div>
                  )}
                  {hasMore && <div ref={sentinelRef} />}
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

// A labeled visualization card — the repeated sys-label + card-soft shell used
// by the map, topics, and timeline sections.
function VizCard({
  label,
  className,
  scroll,
  children,
}: {
  label: string;
  className?: string;
  scroll?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={className}>
      <div className="sys-label mb-1.5">{label}</div>
      <div className={`card-soft p-3${scroll ? " overflow-x-auto" : ""}`}>{children}</div>
    </section>
  );
}

function VitalCard({
  label,
  value,
  hint,
  tint,
}: {
  label: string;
  value: number;
  hint?: string;
  tint: string;
}) {
  return (
    <div className="card p-3.5">
      <div
        className="font-display text-[26px] font-bold leading-[1.1] tracking-[-0.02em]"
        style={{ color: tint }}
      >
        {value}
      </div>
      <div className="sys-label mt-0.5">{label}</div>
      {hint && <div className="mt-0.5 text-[10.5px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

function FeedCard({ event }: { event: ActivityEvent }) {
  const name = event.actor.display_name;
  const avClass = avatarClassFor(name);
  const initials = name.slice(0, 2).toUpperCase();
  const verb = verbFor(event.kind);
  const tag = tagFor(event.kind);
  const href = hrefFor(event);

  return (
    <article className="card flex items-start gap-3 px-4 py-3.5">
      <span
        className={`avatar ${avClass}`}
        style={{ width: 28, height: 28, fontSize: 11 }}
      >
        {initials}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-2 text-[13px] text-dim">
          <span>
            <strong className="text-foreground">{name}</strong> {verb}
          </span>
          <span className="sys-label" style={{ fontSize: 10.5 }}>
            {relativeTime(event.ts)}
          </span>
          {tag && <span className={`tag tag-${tag.kind}`}>{tag.label}</span>}
        </div>
        <h3 className="my-1.5 font-display text-[17px] font-bold leading-tight tracking-[-0.01em]">
          <span className="mr-1.5 inline-flex align-middle text-muted-foreground">
            <EventGlyph kind={event.kind} />
          </span>
          {event.target_label || event.target_id}
        </h3>
        <div className="mt-2 flex flex-wrap items-center gap-2.5 text-[11.5px] text-muted-foreground">
          <span className="flex-1" />
          {href && (
            <Link
              href={href}
              className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[12px] text-dim hover:bg-raised hover:text-foreground"
            >
              Open →
            </Link>
          )}
        </div>
      </div>
    </article>
  );
}

function verbFor(kind: string): string {
  if (kind === "session.uploaded") return "pushed a session";
  if (kind === "page.updated") return "edited a page";
  if (kind === "file.uploaded") return "uploaded a file";
  if (kind === "skill.published") return "published a Skill";
  return kind;
}

function tagFor(kind: string): { kind: "agent" | "human"; label: string } | null {
  if (kind === "session.uploaded") return { kind: "agent", label: "agent" };
  if (kind === "page.updated" || kind === "file.uploaded")
    return { kind: "human", label: "human" };
  return null;
}

function hrefFor(event: ActivityEvent): string | null {
  if (event.kind === "session.uploaded")
    return `/sessions/${encodeURIComponent(event.target_id)}`;
  if (event.kind === "page.updated")
    return `/p/${event.target_id}`;
  if (event.kind === "file.uploaded")
    return `/f/${event.target_id}`;
  return null;
}

function EventGlyph({ kind }: { kind: string }) {
  if (kind === "session.uploaded")
    return (
      <span style={{ color: "var(--color-agent)" }}>
        <SessionsIcon />
      </span>
    );
  if (kind === "page.updated")
    return (
      <span className="text-muted-foreground">
        <PageIcon />
      </span>
    );
  if (kind === "file.uploaded")
    return (
      <span className="text-muted-foreground">
        <FileIcon />
      </span>
    );
  if (kind === "skill.published")
    return (
      <span style={{ color: "var(--color-brand-600)" }}>
        <SkillIcon />
      </span>
    );
  return null;
}
