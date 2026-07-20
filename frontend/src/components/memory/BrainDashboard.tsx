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
import EmbeddingSpaceExplorer from "@/components/viz/EmbeddingSpaceExplorer";
import WikiGraph from "@/components/memory/WikiGraph";
import WikiFileTree from "@/components/memory/WikiFileTree";
import {
  getEmbeddingProjection,
  getMemoryGraph,
  getMemoryTree,
  listActivity,
  type ActivityEvent,
  type WikiGraph as WikiGraphData,
} from "@/lib/api";
import type { EmbeddingProjection, Tree } from "@/lib/types";
import { routes } from "@/lib/workspace-routes";

const PAGE_SIZE = 50;

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
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);
  const [graph, setGraph] = useState<WikiGraphData | null>(null);
  const [wikiTree, setWikiTree] = useState<Tree | null>(null);
  const [projectionLoaded, setProjectionLoaded] = useState(false);
  const [graphLoaded, setGraphLoaded] = useState(false);
  const [treeLoaded, setTreeLoaded] = useState(false);
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
  // scope, include readable shared rows). Each card renders as soon as its
  // own fetch settles — gating them together let one slow or failing
  // endpoint hold the whole dashboard in skeletons.
  useEffect(() => {
    let cancelled = false;
    getEmbeddingProjection(2000)
      .then((p) => {
        if (!cancelled) setProjection(p);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setProjectionLoaded(true);
      });
    getMemoryGraph()
      .then((g) => {
        if (!cancelled) setGraph(g);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setGraphLoaded(true);
      });
    getMemoryTree()
      .then((t) => {
        if (!cancelled) setWikiTree(t);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setTreeLoaded(true);
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
              {!graphLoaded ? (
                <SkeletonBlock className="h-[560px] w-full" />
              ) : graph && graph.nodes.length > 0 ? (
                <WikiGraph data={graph} />
              ) : (
                <div className="flex h-[560px] items-center justify-center px-2 text-center text-[12.5px] text-muted-foreground">
                  No wiki pages yet. Hit &quot;Curate wiki&quot; in the explorer and the
                  agent will compile your history into a context graph of linked pages.
                </div>
              )}
            </VizCard>

            {/* Wiki file system — the same pages, laid out as browsable
                folders. Links to the full-page view at /memory/wiki. */}
            <section>
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="sys-label">Wiki file system</span>
                <Link
                  href="/memory/wiki"
                  className="text-xs text-dim transition-colors duration-150 ease-out hover:text-foreground active:text-foreground/80"
                >
                  Open full view →
                </Link>
              </div>
              <div className="card-soft max-h-[420px] overflow-y-auto p-3">
                {!treeLoaded ? (
                  <SkeletonBlock className="h-[180px] w-full" />
                ) : wikiTree &&
                  (wikiTree.folders.length > 0 || wikiTree.pages.length > 0) ? (
                  <WikiFileTree tree={wikiTree} />
                ) : (
                  <div className="flex h-[180px] items-center justify-center px-2 text-center text-[12.5px] text-muted-foreground">
                    Nothing filed yet. Wiki pages show up here as folders and
                    pages once the curator runs.
                  </div>
                )}
              </div>
            </section>
          </div>

          <div className="flex min-h-0 min-w-0 flex-col gap-4">
            {/* Brain map — the knowledge the brain holds, laid out in space. (Decorative.) */}
            <VizCard label="Knowledge map">
              {!projectionLoaded ? (
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
              <div className="sys-label mb-1.5">Recent edits</div>
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

function FeedCard({ event }: { event: ActivityEvent }) {
  const verb = verbFor(event.kind);
  const href = hrefFor(event);

  return (
    <article className="card px-4 py-3.5">
      <div className="flex flex-wrap items-baseline gap-2 text-[12.5px] text-dim">
        <span>
          <strong className="font-medium text-foreground">
            {event.agent_name ?? "Stash admin"}
          </strong>{" "}
          {verb}
        </span>
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {relativeTime(event.ts)}
        </span>
      </div>
      <h3 className="my-1.5 font-display text-[16px] font-bold leading-tight tracking-[-0.01em]">
        <span className="mr-1.5 inline-flex align-middle text-muted-foreground">
          <EventGlyph kind={event.kind} />
        </span>
        {event.target_label || event.target_id}
      </h3>
      {href && (
        <div className="mt-1 flex justify-end">
          <Link
            href={href}
            className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs text-dim transition-colors duration-150 ease-out hover:bg-raised hover:text-foreground active:bg-raised/80"
          >
            Open →
          </Link>
        </div>
      )}
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

function hrefFor(event: ActivityEvent): string | null {
  if (event.kind === "session.uploaded")
    return routes.session(event.target_id);
  if (event.kind === "page.updated")
    return routes.page(event.target_id);
  if (event.kind === "file.uploaded")
    return routes.file(event.target_id);
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
