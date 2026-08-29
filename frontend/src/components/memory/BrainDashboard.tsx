"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ActivitySkeleton } from "@/components/SkeletonStates";
import { SessionsIcon, SkillIcon, StashIcon } from "@/components/SkillIcons";
import ActiveSkills from "@/components/memory/ActiveSkills";
import DataAndPrivacy from "@/components/memory/DataAndPrivacy";
import CopyableCommandBlock from "@/components/CopyableCommandBlock";
import {
  getHistoryImportProgress,
  getMe,
  getMeOverview,
  getOnboardingStatus,
  listUploadSources,
  listRecentActivity,
  type HistoryImportProgress,
  type MeOverview,
  type OnboardingStatus,
  type RecentActivityEvent,
  type UploadSource,
} from "@/lib/api";

const ACTIVITY_LIMIT = 20;
const ACTIVITY_POLL_MS = 10_000;

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

/** The home dashboard — what is switched on right now: the active Skills,
 *  the Stash installations uploading traces, and the recent-activity feed.
 *  Renders full-page as the app's home route; the shell guarantees a
 *  signed-in user. Scrolls itself (h-full). Themes and the curator log live
 *  on the Usage page. */
export default function BrainDashboard() {
  const [events, setEvents] = useState<RecentActivityEvent[]>([]);
  const [fetching, setFetching] = useState(true);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [firstName, setFirstName] = useState<string | null>(null);
  const [vitals, setVitals] = useState<MeOverview | null>(null);
  const [vitalsError, setVitalsError] = useState<string | null>(null);
  const [vitalsLoaded, setVitalsLoaded] = useState(false);
  const [importing, setImporting] = useState<HistoryImportProgress | null>(null);
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(null);
  const [uploadSources, setUploadSources] = useState<UploadSource[] | null>(null);

  // The vitals decide whether this stash is brand new, so losing them isn't
  // cosmetic: without them Home would drop a first-run user into a grid of
  // empty panels instead of the setup instruction.
  useEffect(() => {
    Promise.all([getMe(), getMeOverview(), getOnboardingStatus(), listUploadSources()])
      .then(([me, overview, nextOnboardingStatus, { sources }]) => {
        setFirstName(me.display_name.split(" ")[0]);
        setVitals(overview);
        setOnboardingStatus(nextOnboardingStatus);
        setUploadSources(sources);
      })
      .catch((e) => setVitalsError(e instanceof Error ? e.message : "Failed to load your stash"))
      .finally(() => setVitalsLoaded(true));
    // One initial look at the CLI's history import; the watcher below keeps
    // polling only while one is running. Decorative — a blip must not error
    // the dashboard.
    getHistoryImportProgress()
      .then(({ progress }) => setImporting(progress && !progress.finished ? progress : null))
      .catch(() => {});
  }, []);

  const stashEmpty =
    vitalsLoaded &&
    vitals !== null &&
    vitals.pages === 0 &&
    vitals.files === 0 &&
    vitals.sessions === 0;
  const initialUploadProgress = getInitialUploadProgress(onboardingStatus, uploadSources);

  // While the stash is empty or a history import is running, keep watching:
  // the CLI's background import fills the stash, and Home should move from
  // setup → import progress → dashboard without a manual refresh.
  const watching = stashEmpty || importing !== null || initialUploadProgress !== null;
  useEffect(() => {
    if (!watching) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const [{ progress }, overview, nextOnboardingStatus, { sources }] = await Promise.all([
          getHistoryImportProgress(),
          getMeOverview(),
          getOnboardingStatus(),
          listUploadSources(),
        ]);
        if (cancelled) return;
        setImporting(progress && !progress.finished ? progress : null);
        setVitals(overview);
        setOnboardingStatus(nextOnboardingStatus);
        setUploadSources(sources);
      } catch {
        // Transient — the next tick retries.
      }
    };
    const timer = setInterval(tick, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [watching]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const feed = await listRecentActivity(ACTIVITY_LIMIT);
        if (!cancelled) {
          setEvents(feed.events);
          setActivityError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setActivityError(error instanceof Error ? error.message : "Failed to load activity");
        }
      } finally {
        if (!cancelled) setFetching(false);
      }
    };
    void load();
    const timer = setInterval(() => void load(), ACTIVITY_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  // The dashboard renders only once both the feed and the vitals have
  // settled, in whichever order they arrive.
  const ready = !fetching && vitalsLoaded;

  if (vitalsError) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center px-8">
        <p className="max-w-md text-center text-[13px] text-destructive">
          Couldn&apos;t load your stash: {vitalsError}
        </p>
      </div>
    );
  }

  // The CLI begins the five-session import before Home has all its data. Keep
  // the progress state visible for the entire import instead of dropping into
  // the dashboard as soon as its first session arrives.
  if (importing) return <ImportingStash progress={importing} />;

  if (initialUploadProgress) {
    return (
      <UploadingFirstSessions
        done={initialUploadProgress.done}
        total={initialUploadProgress.total}
      />
    );
  }

  if (stashEmpty) return <EmptyStashSetup />;

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

        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
            <ActiveSkills />
            <DataAndPrivacy />
          </div>

          <section className="flex min-h-0 min-w-0 flex-col">
            <div className="sys-label mb-1.5">Recent activity</div>
            <div className="card-soft max-h-[640px] overflow-y-auto p-3">
              <div className="flex flex-col gap-2.5">
                {activityError ? (
                  <div className="rounded-[10px] border border-destructive/30 bg-destructive/10 px-4 py-6 text-center text-[13px] text-destructive">
                    {activityError}
                  </div>
                ) : events.length === 0 ? (
                  <div className="rounded-[10px] border border-border bg-base px-4 py-6 text-center text-[13px] text-muted-foreground">
                    Your latest agent sessions and new Skills will appear here.
                  </div>
                ) : (
                  events.map((event) => (
                    <FeedCard key={`${event.kind}-${event.href}`} event={event} />
                  ))
                )}
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function FeedCard({ event }: { event: RecentActivityEvent }) {
  const isSession = event.kind === "session";
  return (
    <article className="card px-4 py-3.5">
      <div className="flex flex-wrap items-baseline gap-2 text-[12.5px] text-dim">
        {event.subtitle && <span>{event.subtitle}</span>}
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {editTimestamp(event.ts)}
        </span>
      </div>
      <h3 className="my-1.5 font-display text-[16px] font-bold leading-tight tracking-[-0.01em]">
        <span className="mr-1.5 inline-flex align-middle text-muted-foreground">
          {isSession ? <SessionsIcon /> : <SkillIcon />}
        </span>
        {event.title}
      </h3>
      <div className="mt-1 flex justify-end">
        <Link
          href={event.href}
          className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[12px] text-dim hover:bg-raised hover:text-foreground"
        >
          {isSession ? "Open trace →" : "Open Skill →"}
        </Link>
      </div>
    </article>
  );
}

/** Full-screen first-run state while `stash import-history` is running: the
 *  import's live progress, front and center — not setup instructions the
 *  user already followed. */
function ImportingStash({ progress }: { progress: HistoryImportProgress }) {
  return <UploadingFirstSessions done={progress.done} total={progress.total} />;
}

function UploadingFirstSessions({ done, total }: { done: number; total: number }) {
  const pct =
    total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  return (
    <div className="flex h-full min-h-0 items-center justify-center overflow-y-auto">
      <div className="w-full max-w-xl px-8 py-10 text-center">
        <StashIcon className="mx-auto text-[44px]" />
        <h1 className="mt-5 font-display text-[26px] font-semibold tracking-tight text-foreground">
          {total === 5 ? "Uploading your first five sessions" : "Uploading your sessions"}
        </h1>
        <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-dim">
          {done.toLocaleString()} of {total.toLocaleString()} sessions uploaded. Stash will use them
          to create your first three Skills.
        </p>
        <div className="mx-auto mt-6 h-2 max-w-md overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full bg-brand transition-[width] duration-700"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          {pct}%
        </p>
      </div>
    </div>
  );
}

export function getInitialUploadProgress(
  status: OnboardingStatus | null,
  sources: UploadSource[] | null,
): { done: number; total: number } | null {
  if (status === null || sources === null) return null;
  if (!sources.some((source) => source.uploads_enabled === true)) return null;
  if (status.curatable_trace_count >= status.trace_target) return null;
  return { done: status.curatable_trace_count, total: status.trace_target };
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
