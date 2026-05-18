"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import {
  FileIcon,
  PageIcon,
  SessionsIcon,
  StashIcon,
} from "../../components/StashIcons";
import { useAuth } from "../../hooks/useAuth";
import {
  getWorkspace,
  listActivity,
  listWorkspaceActivity,
  type ActivityEvent,
} from "../../lib/api";

type FilterKey = "all" | "sessions" | "pages" | "stashes";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "Everything" },
  { key: "sessions", label: "Sessions" },
  { key: "pages", label: "Pages" },
  { key: "stashes", label: "Stashes" },
];

const AVATAR_CLASSES = [
  "av-rose",
  "av-indigo",
  "av-emerald",
  "av-amber",
  "av-sky",
  "av-fuchsia",
  "av-violet",
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
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center text-muted">Loading…</div>}>
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

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const stats = useMemo(() => {
    const dayMs = 24 * 60 * 60 * 1000;
    const since = nowMs - dayMs;
    const recent = events.filter((e) => new Date(e.ts).getTime() >= since);
    return {
      sessions24h: recent.filter((e) => e.kind === "session.uploaded").length,
      pages24h: recent.filter((e) => e.kind === "page.updated").length,
      files24h: recent.filter((e) => e.kind === "file.uploaded").length,
      total: events.length,
    };
  }, [events, nowMs]);

  const filtered = useMemo(() => {
    if (filter === "all") return events;
    if (filter === "sessions")
      return events.filter((e) => e.kind === "session.uploaded");
    if (filter === "pages")
      return events.filter(
        (e) => e.kind === "page.updated" || e.kind === "file.uploaded"
      );
    if (filter === "stashes")
      return events.filter((e) => e.kind === "stash.published");
    return events;
  }, [events, filter]);

  if (loading) return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-9">
        {/* Hero */}
        <div className="sys-label">Activity</div>
        <h1 className="mt-1.5 font-display text-[32px] font-black leading-[1.05] tracking-[-0.025em]">
          {workspaceId
            ? `What's new in ${workspaceName || "this workspace"}.`
            : "Recent work across your workspaces."}
        </h1>
        <p className="mt-1 max-w-[620px] text-[14.5px] text-dim">
          {fetching
            ? "Loading…"
            : `${stats.sessions24h} session${stats.sessions24h === 1 ? "" : "s"}, ${stats.pages24h} page edit${stats.pages24h === 1 ? "" : "s"}, and ${stats.files24h} file upload${stats.files24h === 1 ? "" : "s"} in the last 24 hours.`}
        </p>

        {/* Stat strip */}
        <div className="mt-5 grid grid-cols-4 gap-2.5">
          <StatCard label="Sessions today" value={stats.sessions24h} tint="var(--color-agent)" />
          <StatCard label="Pages edited" value={stats.pages24h} tint="var(--color-human)" />
          <StatCard label="Files uploaded" value={stats.files24h} tint="#16A34A" />
          <StatCard label="Total events" value={stats.total} tint="var(--text-muted)" />
        </div>

        {/* Filters */}
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
          <span className="sys-label">sorted · recent</span>
        </div>

        {/* Feed */}
        <div className="mt-3.5 flex flex-col gap-2.5">
          {fetching ? (
            <div className="rounded-[10px] border border-border bg-base px-4 py-6 text-center text-[13px] text-muted">
              Loading…
            </div>
          ) : filtered.length === 0 ? (
            <div className="rounded-[10px] border border-border bg-base px-4 py-6 text-center text-[13px] text-muted">
              {events.length === 0
                ? "No activity yet. Push a transcript, edit a page, or upload a file."
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

function StatCard({
  label,
  value,
  tint,
}: {
  label: string;
  value: number;
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
    </div>
  );
}

function FeedCard({ event, showWorkspace }: { event: ActivityEvent; showWorkspace: boolean }) {
  const name = event.actor.display_name || event.actor.name;
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
