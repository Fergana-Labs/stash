"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivitySkeleton } from "@/components/SkeletonStates";
import { FileIcon, PageIcon } from "@/components/SkillIcons";
import CuratorLog from "@/components/memory/CuratorLog";
import CopyableCommandBlock from "@/components/CopyableCommandBlock";
import { StashIcon } from "@/components/SkillIcons";
import {
  getMe,
  getMeOverview,
  listFileActivity,
  type ActivityEvent,
  type MeOverview,
} from "@/lib/api";

const PAGE_SIZE = 50;

// The feed pages back indefinitely, so a bare "Mar 3" would read as this
// year's March once the reader scrolls past the year boundary.
function editTimestamp(iso: string): string {
  const at = new Date(iso);
  const year = at.getFullYear() === new Date().getFullYear() ? undefined : "numeric";
  return at.toLocaleString(undefined, {
    year,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** The home dashboard — your stash's vitals, the curator log, and the
 *  file-activity feed. Renders full-page as the app's home route; the shell
 *  guarantees a signed-in user. Scrolls itself (h-full). The graphs of the
 *  same content live in Visualizations; browsing the Memory folder itself
 *  happens in the VFS. */
export default function BrainDashboard() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [fetching, setFetching] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [firstName, setFirstName] = useState<string | null>(null);
  const [vitals, setVitals] = useState<MeOverview | null>(null);
  const [vitalsError, setVitalsError] = useState<string | null>(null);
  const [vitalsLoaded, setVitalsLoaded] = useState(false);

  // The vitals decide whether this stash is brand new, so losing them isn't
  // cosmetic: without them Home would drop a first-run user into a grid of
  // empty panels instead of the setup instruction.
  useEffect(() => {
    Promise.all([getMe(), getMeOverview()])
      .then(([me, overview]) => {
        setFirstName(me.display_name.split(" ")[0]);
        setVitals(overview);
      })
      .catch((e) => setVitalsError(e instanceof Error ? e.message : "Failed to load your stash"))
      .finally(() => setVitalsLoaded(true));
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

  // The dashboard renders only once both the feed and the vitals have
  // settled, in whichever order they arrive.
  const ready = !fetching && vitalsLoaded;

  // The sentinel exists only while the dashboard is rendered, so this has to
  // re-run when the skeleton clears: if the vitals settle last, `loadMore`
  // keeps its identity across that render and the observer would never
  // attach — infinite scroll dead, feed silently capped at one page.
  useEffect(() => {
    if (!ready || !sentinelRef.current) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) loadMore();
      },
      { rootMargin: "200px" }
    );
    obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [loadMore, ready]);

  if (vitalsError) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center px-8">
        <p className="max-w-md text-center text-[13px] text-destructive">
          Couldn&apos;t load your stash: {vitalsError}
        </p>
      </div>
    );
  }

  // A brand-new stash has nothing to dashboard. Until the first transcripts
  // arrive, Home is a single instruction: upload your agent transcripts.
  if (vitalsLoaded && vitals && vitals.pages === 0 && vitals.files === 0 && vitals.sessions === 0) {
    return <EmptyStashSetup />;
  }

  if (!ready) {
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

        {vitals && (
          <div className="mt-4 grid max-w-lg grid-cols-3 gap-3">
            <Vital count={vitals.pages} label="pages" />
            <Vital count={vitals.files} label="files" />
            <Vital count={vitals.sessions} label="sessions" />
          </div>
        )}

        {/* Dashboard grid: the file-activity feed on the left, the curator log
            beside it. The graphs of this same content live in Visualizations. */}
        <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* File activity — what's landing in the filesystem, live. The
              Memory subtree is excluded server-side, so the curator's own
              writes never echo here. Flows with the page: it's the feed you
              come to Home to read, so it pages instead of scrolling in a box. */}
          <section className="flex min-w-0 flex-col lg:col-span-2">
            <div className="sys-label mb-1.5">File activity</div>
            <div className="card-soft p-3">
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

          {/* The curator log — the curator's own account of each nightly run. */}
          <div className="min-w-0">
            <CuratorLog />
          </div>
        </div>
      </div>
    </div>
  );
}

// One vitals counter — how much of a given thing the stash holds.
function Vital({ count, label }: { count: number; label: string }) {
  return (
    <div className="card-soft px-3.5 py-2.5">
      <div className="font-display text-[20px] font-semibold tabular-nums tracking-tight text-foreground">
        {count.toLocaleString()}
      </div>
      <div className="text-[12px] text-muted-foreground">{label}</div>
    </div>
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

/** Full-screen first-run state: one instruction, upload your agent
 *  transcripts. Everything else Home shows grows out of those. */
function EmptyStashSetup() {
  return (
    <div className="flex h-full min-h-0 items-center justify-center overflow-y-auto">
      <div className="w-full max-w-xl px-8 py-10 text-center">
        <StashIcon className="mx-auto text-[44px]" />
        <h1 className="mt-5 font-display text-[26px] font-semibold tracking-tight text-foreground">
          Let&apos;s get you started
        </h1>
        <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-dim">
          Upload your session transcripts to get started. Transcripts are private to you,
          and you can choose which folders transcripts are uploaded from.
        </p>
        <div className="mx-auto mt-6 max-w-md text-left">
          {/* One command on purpose: the installer ends by exec'ing
              `stash signin`, which runs the whole setup wizard. */}
          <CopyableCommandBlock commands={`bash -c "$(curl -fsSL https://joinstash.ai/install)"`} />
        </div>
        <p className="mt-4 text-[12.5px] text-muted-foreground">
          The installer signs you in and sets up session recording. Then use your coding
          agent like you always do — this page becomes your agents&apos; shared memory as
          transcripts arrive.
        </p>
      </div>
    </div>
  );
}
