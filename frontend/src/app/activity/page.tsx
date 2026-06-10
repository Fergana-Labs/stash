"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import AppShell from "../../components/AppShell";
import {
  ActivitySkeleton,
  BasicPageSkeleton,
  SkeletonBlock,
} from "../../components/SkeletonStates";
import {
  FileIcon,
  PageIcon,
  SessionsIcon,
  StashIcon,
} from "../../components/StashIcons";
import ContributorActivityTimeline from "../../components/viz/ContributorActivityTimeline";
import EmbeddingSpaceExplorer from "../../components/viz/EmbeddingSpaceExplorer";
import { useAuth } from "../../hooks/useAuth";
import {
  getActivityTimeline,
  getEmbeddingProjection,
  getMeOverview,
  listActivity,
  type ActivityEvent,
  type MeOverview,
} from "../../lib/api";
import type { ActivityTimeline, EmbeddingProjection } from "../../lib/types";

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

export default function ActivityPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [fetching, setFetching] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [timeline, setTimeline] = useState<ActivityTimeline | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);
  const [overview, setOverview] = useState<MeOverview | null>(null);
  const [insightsLoaded, setInsightsLoaded] = useState(false);
  // Captured once so the "last 24h" window doesn't drift across re-renders.
  const [nowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!user) return;
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
  }, [user]);

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
  // workspace, include readable shared rows).
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setInsightsLoaded(false);
    Promise.allSettled([
      getActivityTimeline(30, "day"),
      getEmbeddingProjection(500),
      getMeOverview(),
    ])
      .then(([t, p, o]) => {
        if (cancelled) return;
        if (t.status === "fulfilled") setTimeline(t.value);
        if (p.status === "fulfilled") setProjection(p.value);
        if (o.status === "fulfilled") setOverview(o.value);
        setInsightsLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const recent24h = useMemo(() => {
    const since = nowMs - 24 * 60 * 60 * 1000;
    return events.filter((e) => new Date(e.ts).getTime() >= since).length;
  }, [events, nowMs]);

  const knowledgePoints = projection?.stats.total_embeddings ?? 0;

  if (loading) return <BasicPageSkeleton />;
  if (!user) return null;
  if (fetching) {
    return (
      <AppShell user={user} onLogout={logout}>
        <ActivitySkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-9">
        {/* Header — what this brain holds and how fresh it is. */}
        <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
          Your brain
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          {`${knowledgePoints.toLocaleString()} things learned across your own and shared knowledge · ${recent24h} new in the last 24 hours.`}
        </p>

        {/* Brain map — the knowledge the brain holds, laid out in space. The
            centerpiece visual. (Decorative.) */}
        <VizCard label="Knowledge map" className="mt-6">
          {!insightsLoaded ? (
            <SkeletonBlock className="h-64 w-full" />
          ) : projection && projection.points.length > 0 ? (
            <EmbeddingSpaceExplorer data={projection} />
          ) : (
            <div className="px-2 py-12 text-center text-[12.5px] text-muted">
              No embeddings indexed yet. Pages, table rows, and session events get
              embedded as they&apos;re added.
            </div>
          )}
        </VizCard>

        {/* Vitals — the brain's current size and pulse. */}
        <div className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-5">
          <VitalCard label="Knowledge points" value={knowledgePoints} tint="var(--color-brand-600)" />
          <VitalCard label="Pages" value={overview?.pages ?? 0} tint="var(--color-human)" />
          <VitalCard label="Files" value={overview?.files ?? 0} tint="#16A34A" />
          <VitalCard label="Sessions" value={overview?.sessions ?? 0} tint="var(--color-agent)" />
          <VitalCard label="Learned today" value={recent24h} tint="var(--text-muted)" />
        </div>

        {/* Human / agent commits over time. (Decorative.) */}
        <VizCard label="Human / agent commits — last 30 days" className="mt-5" scroll>
          {!insightsLoaded ? (
            <SkeletonBlock className="h-40 w-full" />
          ) : timeline && timeline.contributors.length > 0 ? (
            <ContributorActivityTimeline data={timeline} />
          ) : (
            <div className="px-2 py-6 text-center text-[12.5px] text-muted">
              No agent session commits yet. Push a transcript to populate this view.
            </div>
          )}
        </VizCard>

        {/* Newsfeed — what the brain has been learning lately. */}
        <div className="mt-8 border-b border-border pb-2">
          <span className="sys-label">Recent learnings</span>
        </div>

        <div className="mt-3.5 flex flex-col gap-2.5">
          {events.length === 0 ? (
            <div className="rounded-[10px] border border-border bg-base px-4 py-6 text-center text-[13px] text-muted">
              Nothing learned yet. Push a transcript, edit a page, or upload a
              file.
            </div>
          ) : (
            events.map((event, i) => (
              <FeedCard
                key={`${event.kind}-${event.target_id}-${i}`}
                event={event}
                showWorkspace
              />
            ))
          )}
          {loadingMore && (
            <div className="py-2 text-center text-[12.5px] text-muted">
              Loading more…
            </div>
          )}
          {hasMore && <div ref={sentinelRef} />}
        </div>
      </div>
    </AppShell>
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
      {hint && <div className="mt-0.5 text-[10.5px] text-muted">{hint}</div>}
    </div>
  );
}

function FeedCard({ event, showWorkspace }: { event: ActivityEvent; showWorkspace: boolean }) {
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
          <span className="mr-1.5 inline-flex align-middle text-muted">
            <EventGlyph kind={event.kind} />
          </span>
          {event.target_label || event.target_id}
        </h3>
        <div className="mt-2 flex flex-wrap items-center gap-2.5 text-[11.5px] text-muted">
          {showWorkspace && event.workspace_name && event.workspace_id && (
            <Link
              href={`/workspaces/${event.workspace_id}`}
              className="font-mono hover:text-foreground"
            >
              {event.workspace_name}
            </Link>
          )}
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
  if (kind === "member.joined") return "joined the workspace";
  if (kind === "stash.published") return "published a Stash";
  return kind;
}

function tagFor(kind: string): { kind: "agent" | "human"; label: string } | null {
  if (kind === "session.uploaded") return { kind: "agent", label: "agent" };
  if (kind === "page.updated" || kind === "file.uploaded")
    return { kind: "human", label: "human" };
  return null;
}

function hrefFor(event: ActivityEvent): string | null {
  if (!event.workspace_id) return null;
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
      <span className="text-muted">
        <PageIcon />
      </span>
    );
  if (kind === "file.uploaded")
    return (
      <span className="text-muted">
        <FileIcon />
      </span>
    );
  if (kind === "stash.published")
    return (
      <span style={{ color: "var(--color-brand-600)" }}>
        <StashIcon />
      </span>
    );
  return null;
}
