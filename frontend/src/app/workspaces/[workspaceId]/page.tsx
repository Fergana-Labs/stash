"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import MembersModal from "../../../components/MembersModal";
import {
  FileIcon,
  PageIcon,
  SessionsIcon,
  StashIcon,
} from "../../../components/StashIcons";
import { useAuth } from "../../../hooks/useAuth";
import {
  type ActivityEvent,
  getWorkspace,
  getWorkspaceMembers,
  joinWorkspace,
  listStashes,
  listWorkspaceActivity,
  type WorkspaceStash,
} from "../../../lib/api";
import type { Workspace, WorkspaceMember } from "../../../lib/types";

type FilterKey = "all" | "sessions" | "pages" | "stashes" | "discover";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "Everything" },
  { key: "sessions", label: "Sessions" },
  { key: "pages", label: "Pages" },
  { key: "stashes", label: "Stashes" },
  { key: "discover", label: "From discover" },
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

export default function WorkspaceHomePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [stashes, setStashes] = useState<WorkspaceStash[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [error, setError] = useState("");
  const [membersOpen, setMembersOpen] = useState(false);

  const load = useCallback(async () => {
    const [w, m, s, a] = await Promise.allSettled([
      getWorkspace(workspaceId),
      getWorkspaceMembers(workspaceId),
      listStashes(workspaceId),
      listWorkspaceActivity(workspaceId, 50),
    ]);
    if (w.status === "fulfilled") setWorkspace(w.value);
    else setError("Workspace not found");
    if (m.status === "fulfilled") setMembers(m.value);
    if (s.status === "fulfilled") setStashes(s.value);
    if (a.status === "fulfilled") setEvents(a.value);
  }, [workspaceId]);

  useEffect(() => {
    if (!user) return;
    load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const isMember = !!user && members.some((m) => m.user_id === user.id);

  async function handleJoin() {
    if (!workspace) return;
    try {
      await joinWorkspace(workspace.invite_code);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to join");
    }
  }

  // "Now" is captured once on mount so the 24h window doesn't drift on every
  // re-render (which would also trip the react-hooks/purity rule on useMemo).
  const [nowMs] = useState(() => Date.now());
  const stats = useMemo(() => {
    const dayMs = 24 * 60 * 60 * 1000;
    const since = nowMs - dayMs;
    const recent = events.filter((e) => new Date(e.ts).getTime() >= since);
    const sessionsToday = recent.filter((e) => e.kind === "session.uploaded").length;
    const pagesEdited = recent.filter((e) => e.kind === "page.updated").length;
    const external = stashes.filter((s) => s.access === "public").length;
    return {
      sessionsToday,
      pagesEdited,
      activeStashes: stashes.length,
      externalStashes: external,
    };
  }, [events, stashes, nowMs]);

  const filtered = useMemo(() => {
    if (filter === "all") return events;
    if (filter === "sessions") return events.filter((e) => e.kind === "session.uploaded");
    if (filter === "pages") return events.filter((e) => e.kind === "page.updated" || e.kind === "file.uploaded");
    if (filter === "stashes") return events.filter((e) => e.kind === "stash.published");
    return [];
  }, [events, filter]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return (
    <>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[920px] px-12 pb-20 pt-9">
          <div className="flex justify-end gap-1.5">
            <Link
              href={`/workspaces/${workspaceId}/stashes`}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-base px-2.5 py-1 text-[12.5px] font-medium text-foreground hover:bg-raised"
            >
              <PlusGlyph /> New Stash
            </Link>
            <button
              onClick={() => setMembersOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-base px-2.5 py-1 text-[12.5px] font-medium text-foreground hover:bg-raised"
            >
              Members
            </button>
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          {!isMember && workspace && (
            <div className="mt-4 flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 text-[13px]">
              <span className="text-muted">You aren&apos;t a member of this workspace.</span>
              <button
                onClick={handleJoin}
                className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
              >
                Join workspace
              </button>
            </div>
          )}

          {/* Stat strip */}
          <div className="mt-4 grid grid-cols-4 gap-2.5">
            <StatCard label="Sessions today" value={stats.sessionsToday} tint="var(--color-agent)" />
            <StatCard label="Pages edited" value={stats.pagesEdited} tint="var(--color-human)" />
            <StatCard label="Active Stashes" value={stats.activeStashes} tint="var(--color-brand-500)" />
            <StatCard label="External" value={stats.externalStashes} tint="var(--text-muted)" />
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
            {filtered.length === 0 ? (
              <div className="rounded-[10px] border border-border bg-base px-4 py-6 text-center text-[13px] text-muted">
                {filter === "discover"
                  ? "Discover suggestions will show here when available."
                  : "No recent activity to show."}
              </div>
            ) : (
              filtered.map((event, i) => (
                <FeedCard
                  key={`${event.kind}-${event.target_id}-${i}`}
                  event={event}
                />
              ))
            )}
          </div>
        </div>
      </div>
      <MembersModal
        workspaceId={workspaceId}
        open={membersOpen}
        onClose={() => setMembersOpen(false)}
      />
    </>
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

function FeedCard({ event }: { event: ActivityEvent }) {
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
          {event.workspace_name && (
            <span className="font-mono">{event.workspace_name}</span>
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

function PlusGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
