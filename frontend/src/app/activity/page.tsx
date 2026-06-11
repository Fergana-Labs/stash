"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
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
import KnowledgeDensityMap from "../../components/viz/KnowledgeDensityMap";
import { useAuth } from "../../hooks/useAuth";
import {
  getActivityTimeline,
  getEmbeddingProjection,
  getKnowledgeDensity,
  getWorkspace,
  getWorkspaceOverview,
  listActivity,
  listMyWorkspaces,
  listWorkspaceActivity,
  listWorkspaceSources,
  type ActivityEvent,
  type WorkspaceOverview,
  type WorkspaceSource,
} from "../../lib/api";
import type {
  ActivityTimeline,
  EmbeddingProjection,
  KnowledgeDensity,
} from "../../lib/types";

type FilterKey = "all" | "sessions" | "pages" | "cartridges";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "Everything" },
  { key: "sessions", label: "Sessions" },
  { key: "pages", label: "Pages" },
  { key: "cartridges", label: "Cartridges" },
];

const AVATAR_CLASSES = [
  "av-rose",
  "av-orange",
  "av-emerald",
  "av-amber",
  "av-sky",
  "av-teal",
  "av-lime",
];

// Native handles ("files"/"sessions") are always present — the Sources vital
// counts the connected integrations the brain draws from, not these.
const NATIVE_SOURCE_TYPES = new Set(["native_files", "native_sessions"]);

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
  return (
    <Suspense fallback={<BasicPageSkeleton />}>
      <ActivityPageInner />
    </Suspense>
  );
}

function ActivityPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = searchParams.get("workspace");
  const { user, loading, logout } = useAuth();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [workspaceName, setWorkspaceName] = useState("");
  const [fetching, setFetching] = useState(true);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [timeline, setTimeline] = useState<ActivityTimeline | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);
  const [density, setDensity] = useState<KnowledgeDensity | null>(null);
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [sources, setSources] = useState<WorkspaceSource[]>([]);
  const [insightsLoaded, setInsightsLoaded] = useState(false);
  // Captured once so the "last 24h" window doesn't drift across re-renders.
  const [nowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    const eventsPromise = workspaceId
      ? listWorkspaceActivity(workspaceId, 200)
      : listActivity(200);
    const workspacePromise = workspaceId ? getWorkspace(workspaceId) : null;

    Promise.all([eventsPromise, workspacePromise])
      .then(([nextEvents, workspace]) => {
        if (cancelled) return;
        setEvents(nextEvents);
        if (workspace) setWorkspaceName(workspace.name);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setFetching(false);
      });

    return () => {
      cancelled = true;
    };
  }, [user, workspaceId]);

  // The brain's vitals + visualizations. All workspace-scoped, so for the
  // global view we resolve the user's own workspace once and fan out.
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setInsightsLoaded(false);
    (async () => {
      const wsId = workspaceId || (await listMyWorkspaces()).workspaces[0]?.id;
      if (!wsId) {
        if (!cancelled) setInsightsLoaded(true);
        return;
      }
      const [t, p, d, o, s] = await Promise.allSettled([
        getActivityTimeline(30, "day", wsId),
        getEmbeddingProjection(500, undefined, wsId),
        getKnowledgeDensity(12, wsId),
        getWorkspaceOverview(wsId),
        listWorkspaceSources(wsId),
      ]);
      if (cancelled) return;
      if (t.status === "fulfilled") setTimeline(t.value);
      if (p.status === "fulfilled") setProjection(p.value);
      if (d.status === "fulfilled") setDensity(d.value);
      if (o.status === "fulfilled") setOverview(o.value);
      if (s.status === "fulfilled") setSources(s.value);
      setInsightsLoaded(true);
    })().catch(() => {
      if (!cancelled) setInsightsLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, [user, workspaceId]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const stats = useMemo(() => {
    const dayMs = 24 * 60 * 60 * 1000;
    const since = nowMs - dayMs;
    const recent = events.filter((e) => new Date(e.ts).getTime() >= since);
    return {
      recent24h: recent.length,
      sessions24h: recent.filter((e) => e.kind === "session.uploaded").length,
      pages24h: recent.filter((e) => e.kind === "page.updated").length,
      files24h: recent.filter((e) => e.kind === "file.uploaded").length,
      total: events.length,
    };
  }, [events, nowMs]);

  // Connected integrations the brain learns from, plus their freshness.
  const sourceVitals = useMemo(() => {
    const connected = sources.filter((s) => !NATIVE_SOURCE_TYPES.has(s.type));
    const syncing = connected.filter((s) => s.sync_status === "syncing").length;
    const syncedAt = connected
      .map((s) => s.last_synced_at)
      .filter((v): v is string => !!v)
      .sort()
      .at(-1);
    let hint = "—";
    if (syncing > 0) hint = `${syncing} syncing`;
    else if (syncedAt) hint = `synced ${relativeTime(syncedAt)}`;
    else if (connected.length > 0) hint = "not synced yet";
    return { count: connected.length, hint };
  }, [sources]);

  const knowledgePoints = projection?.stats.total_embeddings ?? 0;

  const filtered = useMemo(() => {
    if (filter === "all") return events;
    if (filter === "sessions")
      return events.filter((e) => e.kind === "session.uploaded");
    if (filter === "pages")
      return events.filter(
        (e) => e.kind === "page.updated" || e.kind === "file.uploaded"
      );
    if (filter === "cartridges")
      return events.filter((e) => e.kind === "stash.published");
    return events;
  }, [events, filter]);

  if (loading) return <BasicPageSkeleton />;
  if (!user) return null;
  if (fetching) {
    return (
      <AppShell user={user} onLogout={logout}>
        <ActivitySkeleton />
      </AppShell>
    );
  }

  const title = workspaceId ? workspaceName || "Your brain" : "Your brain";

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-9">
        {/* Header — what this brain holds and how fresh it is. */}
        <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          {`${knowledgePoints.toLocaleString()} things learned across ${sourceVitals.count} connected source${sourceVitals.count === 1 ? "" : "s"} · ${stats.recent24h} new in the last 24 hours.`}
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
        <div className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
          <VitalCard label="Knowledge points" value={knowledgePoints} tint="var(--color-brand-600)" />
          <VitalCard label="Pages" value={overview?.files.pages.length ?? 0} tint="var(--color-human)" />
          <VitalCard label="Files" value={overview?.files.files.length ?? 0} tint="#16A34A" />
          <VitalCard label="Sessions" value={overview?.sessions.length ?? 0} tint="var(--color-agent)" />
          <VitalCard label="Sources" value={sourceVitals.count} hint={sourceVitals.hint} tint="#7C3AED" />
          <VitalCard label="Learned today" value={stats.recent24h} tint="var(--text-muted)" />
        </div>

        {/* What the brain knows — topic clusters. Hidden when there's nothing
            to show, since it's an optional lens. */}
        {density && density.clusters.length > 0 && (
          <VizCard label="What your brain knows" className="mt-7">
            <KnowledgeDensityMap data={density} />
          </VizCard>
        )}

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
        <div className="mt-8 flex items-center justify-between border-b border-border pb-2">
          <div className="flex gap-1">
            {FILTERS.map((f) => {
              const active = filter === f.key;
              return (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={
                    "rounded-md px-2.5 py-1 text-[12.5px] " +
                    (active
                      ? "bg-raised font-semibold text-foreground"
                      : "text-muted hover:text-foreground")
                  }
                >
                  {f.label}
                </button>
              );
            })}
          </div>
          <span className="sys-label">Recent learnings · recent</span>
        </div>

        <div className="mt-3.5 flex flex-col gap-2.5">
          {filtered.length === 0 ? (
            <div className="rounded-[10px] border border-border bg-base px-4 py-6 text-center text-[13px] text-muted">
              {events.length === 0
                ? "Nothing learned yet. Push a transcript, edit a page, or upload a file."
                : `No ${filter === "all" ? "" : filter + " "}activity matches this filter.`}
            </div>
          ) : (
            filtered.map((event, i) => (
              <FeedCard
                key={`${event.kind}-${event.target_id}-${i}`}
                event={event}
                showWorkspace={!workspaceId}
              />
            ))
          )}
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
    return `/workspaces/${event.workspace_id}/sessions/${encodeURIComponent(event.target_id)}`;
  if (event.kind === "page.updated")
    return `/workspaces/${event.workspace_id}/p/${event.target_id}`;
  if (event.kind === "file.uploaded")
    return `/workspaces/${event.workspace_id}/f/${event.target_id}`;
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
