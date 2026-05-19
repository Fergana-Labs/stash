"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import SessionUpload from "../../../../components/SessionUpload";
import { SessionsListSkeleton } from "../../../../components/SkeletonStates";
import { SettingsIcon } from "../../../../components/StashIcons";
import { useAuth } from "../../../../hooks/useAuth";
import { listMySessions, type SessionSummary } from "../../../../lib/api";
import {
  groupSessionsByAgent,
  groupSessionsByDayAndUser,
  groupSessionsByUser,
  requireSessionUserName,
  type SessionDayGroup,
  type SessionFlatGroup,
} from "../../../../lib/sessionGrouping";

type ViewKey = "list" | "day" | "user" | "agent";
type SortKey = "recent" | "oldest" | "events" | "name";

const VIEW_STORAGE_KEY = "stash_sessions_view";

const VIEWS: { key: ViewKey; label: string }[] = [
  { key: "list", label: "List" },
  { key: "day", label: "By day" },
  { key: "user", label: "By user" },
  { key: "agent", label: "By agent" },
];

const SORTS: { key: SortKey; label: string }[] = [
  { key: "recent", label: "Recent" },
  { key: "oldest", label: "Oldest" },
  { key: "events", label: "Most events" },
  { key: "name", label: "Name" },
];

export default function StashSessionsPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading } = useAuth();

  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<ViewKey>("list");
  const [sort, setSort] = useState<SortKey>("recent");

  useBreadcrumbs([{ label: "Sessions" }], `${workspaceId}/sessions`);

  // Restore last-used view from localStorage on mount. Sort + search are
  // intentionally not persisted — they read more like ad-hoc filters than
  // long-lived preferences.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(VIEW_STORAGE_KEY) as ViewKey | null;
    if (saved && VIEWS.some((v) => v.key === saved)) setView(saved);
  }, []);

  const load = useCallback(async () => {
    try {
      const list = await listMySessions(workspaceId, 200);
      setSessions(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sessions");
    }
  }, [workspaceId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const sorted = useMemo(() => {
    if (!sessions) return null;
    const copy = [...sessions];
    if (sort === "recent") copy.sort((a, b) => sessionTime(b) - sessionTime(a));
    else if (sort === "oldest") copy.sort((a, b) => sessionTime(a) - sessionTime(b));
    else if (sort === "events") copy.sort((a, b) => b.event_count - a.event_count);
    else copy.sort((a, b) => sessionTitle(a).localeCompare(sessionTitle(b)));
    return copy;
  }, [sessions, sort]);

  if (loading) return <SessionsListSkeleton />;
  if (!user) return null;
  if (sorted === null) return <SessionsListSkeleton />;

  const total = sessions?.length ?? 0;

  function setViewPersisted(next: ViewKey) {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_STORAGE_KEY, next);
    } catch {
      /* localStorage unavailable */
    }
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-12 py-8">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
            Sessions
          </h1>
          <span className="sys-label" style={{ fontSize: 10.5 }}>
            {total} total
          </span>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        <div className="mt-5 mb-4">
          <SessionUpload workspaceId={workspaceId} onUploaded={load} />
        </div>

        {/* Toolbar: View · Sort. Drives the rendering below. */}
        <div className="mb-3 flex flex-wrap items-center gap-3 border-b border-border pb-2.5">
          <SegmentedControl
            label="View"
            value={view}
            options={VIEWS}
            onChange={(v) => setViewPersisted(v as ViewKey)}
          />
          <SegmentedControl
            label="Sort"
            value={sort}
            options={SORTS}
            onChange={(v) => setSort(v as SortKey)}
          />
        </div>

        {sorted && (
          <SessionsView
            view={view}
            sessions={sorted}
            workspaceId={workspaceId}
          />
        )}
      </div>
    </div>
  );
}

function SessionsView({
  view,
  sessions,
  workspaceId,
}: {
  view: ViewKey;
  sessions: SessionSummary[];
  workspaceId: string;
}) {
  if (sessions.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted">
        No sessions yet.
      </div>
    );
  }

  if (view === "list") {
    return <SessionsTable workspaceId={workspaceId} sessions={sessions} />;
  }

  if (view === "day") {
    const groups = groupSessionsByDayAndUser(sessions);
    return (
      <div className="flex flex-col gap-4">
        {groups.map((group, i) => (
          <DayGroup
            key={group.key}
            group={group}
            workspaceId={workspaceId}
            initialOpen={i === 0}
          />
        ))}
      </div>
    );
  }

  const groups = view === "user" ? groupSessionsByUser(sessions) : groupSessionsByAgent(sessions);
  return (
    <div className="flex flex-col gap-4">
      {groups.map((group, i) => (
        <FlatGroup
          key={group.key}
          group={group}
          workspaceId={workspaceId}
          initialOpen={i === 0}
        />
      ))}
    </div>
  );
}

function DayGroup({
  group,
  workspaceId,
  initialOpen,
}: {
  group: SessionDayGroup;
  workspaceId: string;
  initialOpen: boolean;
}) {
  const [open, setOpen] = useState(initialOpen);
  return (
    <section>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-raised"
      >
        <Chev open={open} />
        <h2 className="m-0 font-display text-[15px] font-semibold">{group.label}</h2>
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {group.count}
        </span>
      </button>
      {open && (
        <div className="mt-1.5 flex flex-col gap-4">
          {group.users.map((bucket) => (
            <div key={bucket.user}>
              <div className="mb-1 px-2 text-[11px] font-medium text-muted">{bucket.user}</div>
              <SessionsTable workspaceId={workspaceId} sessions={bucket.sessions} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function FlatGroup({
  group,
  workspaceId,
  initialOpen,
}: {
  group: SessionFlatGroup;
  workspaceId: string;
  initialOpen: boolean;
}) {
  const [open, setOpen] = useState(initialOpen);
  return (
    <section>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-raised"
      >
        <Chev open={open} />
        <h2 className="m-0 font-display text-[15px] font-semibold">{group.label}</h2>
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {group.count}
        </span>
      </button>
      {open && (
        <div className="mt-1.5">
          <SessionsTable workspaceId={workspaceId} sessions={group.sessions} />
        </div>
      )}
    </section>
  );
}

function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { key: T; label: string }[];
  onChange: (next: T) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1.5 text-[12px]">
      <span className="sys-label" style={{ fontSize: 10 }}>
        {label}
      </span>
      <div className="inline-flex gap-0.5 rounded-md border border-border bg-base p-[2px]">
        {options.map((opt) => {
          const active = value === opt.key;
          return (
            <button
              key={opt.key}
              type="button"
              onClick={() => onChange(opt.key)}
              className={
                "rounded px-2 py-[3px] text-[12px] " +
                (active
                  ? "bg-raised font-semibold text-foreground"
                  : "text-muted hover:text-foreground")
              }
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Chev({ open }: { open: boolean }) {
  return (
    <svg
      className={"h-3 w-3 text-muted transition-transform " + (open ? "rotate-90" : "")}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function SessionsTable({
  workspaceId,
  sessions,
}: {
  workspaceId: string;
  sessions: SessionSummary[];
}) {
  if (sessions.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted">
        No sessions yet.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="hidden grid-cols-[minmax(128px,0.68fr)_minmax(240px,1.7fr)_82px_58px_minmax(104px,0.62fr)_94px_88px_28px] gap-3 border-b border-border bg-base/70 px-3 py-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted md:grid">
        <span>User</span>
        <span>Session</span>
        <span>Access</span>
        <span>Events</span>
        <span>Agent</span>
        <span>Date</span>
        <span>Updated</span>
        <span />
      </div>
      {sessions.map((session) => (
        <SessionTableRow
          key={session.session_id}
          workspaceId={workspaceId}
          session={session}
        />
      ))}
    </div>
  );
}

function SessionTableRow({
  workspaceId,
  session,
}: {
  workspaceId: string;
  session: SessionSummary;
}) {
  const user = requireSessionUserName(session.user_name);
  const agent = session.agent_name || "agent";
  const avatar = avatarFor(user);

  return (
    <Link
      href={`/workspaces/${workspaceId}/sessions/${encodeURIComponent(session.session_id)}`}
      className="grid min-h-12 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-3 py-2 text-[13px] last:border-b-0 hover:bg-[var(--color-brand-50)] md:grid-cols-[minmax(128px,0.68fr)_minmax(240px,1.7fr)_82px_58px_minmax(104px,0.62fr)_94px_88px_28px]"
    >
      <div className="hidden min-w-0 items-center gap-2 md:flex">
        <span
          className={
            "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold " +
            avatar.bg +
            " " +
            avatar.fg
          }
        >
          {initialsFor(user)}
        </span>
        <span className="truncate text-foreground">{user}</span>
      </div>
      <div className="min-w-0">
        <div className="truncate font-medium text-foreground">{sessionTitle(session)}</div>
        <div className="mt-0.5 truncate text-[11px] text-muted md:hidden">
          {user} · {agent} · {formatRelative(session.last_event_at)}
        </div>
      </div>
      <span className="hidden w-fit rounded-full border border-border bg-base px-2 py-0.5 text-[11px] text-muted md:inline-flex">
        Private
      </span>
      <span className="hidden items-center gap-1 text-[12px] text-muted md:flex">
        <MessageIcon />
        {session.event_count}
      </span>
      <span className="hidden truncate text-muted md:block">{agent}</span>
      <span className="hidden whitespace-nowrap text-[12px] text-muted md:block">
        {formatDate(session.last_event_at || session.started_at)}
      </span>
      <span className="justify-self-end whitespace-nowrap text-[12px] text-muted">
        {formatRelative(session.last_event_at)}
      </span>
      <span className="hidden justify-self-end text-muted md:block">
        <SettingsIcon />
      </span>
    </Link>
  );
}

function sessionTitle(s: SessionSummary): string {
  const preview = (s.first_prompt_preview || "").trim().replace(/\s+/g, " ");
  if (preview) return preview.length > 96 ? preview.slice(0, 96) + "…" : preview;
  const id = s.session_id;
  return id.replace(/^session[-_]/, "").replace(/[-_]+/g, " ") || id;
}

function sessionTime(session: SessionSummary): number {
  const time = new Date(session.last_event_at || session.started_at).getTime();
  return Number.isNaN(time) ? 0 : time;
}

const AVATAR_PALETTE: { bg: string; fg: string }[] = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];

function avatarFor(name: string) {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function initialsFor(name: string): string {
  const normalized = name.trim();
  if (!normalized) return "?";
  return normalized.slice(0, 2).toUpperCase();
}

function MessageIcon() {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
    </svg>
  );
}

function formatRelative(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return new Date(iso).toLocaleDateString();
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}
