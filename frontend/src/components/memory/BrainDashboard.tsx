"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ActivitySkeleton, SkeletonBlock } from "@/components/SkeletonStates";
import { FileIcon, PageIcon } from "@/components/SkillIcons";
import EmbeddingSpaceExplorer from "@/components/viz/EmbeddingSpaceExplorer";
import CuratorLog from "@/components/memory/CuratorLog";
import WikiGraph from "@/components/memory/WikiGraph";
import {
  getEmbeddingProjection,
  getMe,
  getMemoryGraph,
  listFileActivity,
  type ActivityEvent,
  type WikiGraph as WikiGraphData,
} from "@/lib/api";
import type { EmbeddingProjection } from "@/lib/types";

const PAGE_SIZE = 50;

function editTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** The home dashboard — the wiki graph, the curator log, the knowledge map,
 *  and the file-activity feed. Renders full-page as the app's home route; the
 *  shell guarantees a signed-in user. Scrolls itself (h-full). Browsing the
 *  Memory folder itself happens in Files. */
export default function BrainDashboard() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [fetching, setFetching] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);
  const [graph, setGraph] = useState<WikiGraphData | null>(null);
  const [projectionLoaded, setProjectionLoaded] = useState(false);
  const [graphLoaded, setGraphLoaded] = useState(false);
  const [firstName, setFirstName] = useState<string | null>(null);

  useEffect(() => {
    getMe().then((me) => setFirstName(me.display_name.split(" ")[0])).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    listFileActivity({ limit: PAGE_SIZE })
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
      const feed = await listFileActivity({
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
    return () => {
      cancelled = true;
    };
  }, []);

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
        <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
          Welcome back{firstName ? `, ${firstName}` : ""}
        </h1>

        {/* Dashboard grid: wiki graph with the curator log beneath it on
            the left, knowledge map + file activity on the right. */}
        <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
            {/* Wiki graph — the curated context graph of linked pages, obsidian
                style. The centerpiece: click a node to open its page. */}
            <VizCard label="Memory wiki">
              {!graphLoaded ? (
                <SkeletonBlock className="h-[560px] w-full" />
              ) : graph && graph.nodes.length > 0 ? (
                <WikiGraph data={graph} />
              ) : (
                <div className="flex h-[560px] items-center justify-center px-2 text-center text-[12.5px] text-muted-foreground">
                  No wiki pages yet. The Memory curator&apos;s nightly run compiles
                  your history into a context graph of linked pages.
                </div>
              )}
            </VizCard>

            {/* The curator log — the curator's own account of each run,
                beneath the structure it maintains. */}
            <CuratorLog />
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

            {/* File activity — what's landing in the filesystem, live. The
                Memory subtree is excluded server-side, so the curator's own
                writes never echo here. Scrolls in place (hard cap — inside a
                grid, flex-1 can't bound it) so the panel stays a dashboard,
                not a page. */}
            <section className="flex flex-col">
              <div className="sys-label mb-1.5">File activity</div>
              <div className="card-soft max-h-[480px] overflow-y-auto p-3">
                <div className="flex flex-col gap-2.5">
                  {events.length === 0 ? (
                    <div className="rounded-[10px] border border-border bg-base px-4 py-6 text-center text-[13px] text-muted-foreground">
                      Nothing here yet. Upload a file or edit a page and it
                      shows up here.
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
          {editTimestamp(event.ts)}
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
            className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[12px] text-dim hover:bg-raised hover:text-foreground"
          >
            Open →
          </Link>
        </div>
      )}
    </article>
  );
}

function verbFor(kind: string): string {
  if (kind === "page.updated") return "edited a page";
  if (kind === "file.uploaded") return "uploaded a file";
  return kind;
}

function hrefFor(event: ActivityEvent): string | null {
  if (event.kind === "page.updated") return `/p/${event.target_id}`;
  if (event.kind === "file.uploaded") return `/f/${event.target_id}`;
  return null;
}

function EventGlyph({ kind }: { kind: string }) {
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
  return null;
}
