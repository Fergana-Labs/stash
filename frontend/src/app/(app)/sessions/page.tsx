"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import CopyableCommandBlock from "@/components/CopyableCommandBlock";
import SessionUpload from "@/components/SessionUpload";
import { SessionsListSkeleton } from "@/components/SkeletonStates";
import { PinIcon } from "@/components/SkillIcons";
import { SelectBox } from "@/components/content/file-browser/ItemsList";
import { useAuth } from "@/hooks/useAuth";
import {
  deleteSession,
  listMySessions,
  type SessionSummary,
} from "@/lib/api";
import { usePins } from "@/lib/pins";
import {
  groupSessionsByAgent,
  groupSessionsByDayAndUser,
  groupSessionsByUser,
  requireSessionUserName,
  type SessionDayGroup,
  type SessionFlatGroup,
} from "@/lib/sessionGrouping";

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

export default function SkillSessionsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const pins = usePins("sessions");
  const confirm = useConfirm();

  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<ViewKey>("list");
  const [sort, setSort] = useState<SortKey>("recent");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  function toggleSelect(sessionId: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  }

  useBreadcrumbs([{ label: "Sessions" }], "sessions");

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
      setSessions(await listMySessions(200));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sessions");
    }
  }, []);

  // Fire on mount, in parallel with useAuth's /users/me — apiFetch resolves
  // its own token, and serializing behind auth doubled time-to-content. A
  // signed-out visitor's 401 is invisible: the !user guard below keeps the
  // error from rendering while the login redirect happens.
  useEffect(() => {
    load();
  }, [load]);

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

  // Render as soon as the sessions themselves land — don't hold a finished
  // list (or the empty state) hostage to the slower /users/me round trip.
  if (!loading && !user) return null;
  if (sorted === null) return <SessionsListSkeleton />;

  const pinnedSessions = (sorted ?? []).filter((s) =>
    pins.pinnedSet.has(s.session_id),
  );
  const selectedSessions = (sorted ?? []).filter((s) =>
    selectedIds.has(s.session_id),
  );
  function clearSelection() {
    setSelectedIds(new Set());
  }

  async function bulkDeleteSessions() {
    const targets = selectedSessions.filter((s) => s.id);
    if (targets.length === 0) return;
    const ok = await confirm({
      title: `Delete ${targets.length} session${targets.length === 1 ? "" : "s"}?`,
      body: "They move to Trash.",
      confirmLabel: "Delete",
    });
    if (!ok) return;
    try {
      for (const session of targets) {
        await deleteSession(session.id!);
      }
      clearSelection();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

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
        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        <div className="mt-5 mb-4">
          <SessionUpload onUploaded={load} />
        </div>

        {pinnedSessions.length > 0 && (
          <section className="mb-5">
            <h2 className="m-0 mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <PinIcon className="text-[13px]" />
              Pinned
            </h2>
            <SessionsTable
              sessions={pinnedSessions}
              isPinned={pins.isPinned}
              onTogglePin={pins.toggle}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
            />
          </section>
        )}

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

        <SessionsView
          view={view}
          sessions={sorted}
          isPinned={pins.isPinned}
          onTogglePin={pins.toggle}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
        />
      </div>

      {selectedSessions.length > 0 && (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center">
          <div className="pointer-events-auto flex items-center gap-3 rounded-lg border border-border bg-foreground px-4 py-2 text-[13px] text-background shadow-lg">
            <span className="font-medium">{selectedSessions.length} selected</span>
            <button
              type="button"
              onClick={() => void bulkDeleteSessions()}
              className="cursor-pointer rounded-md border border-background/40 px-2 py-0.5 text-[12px] font-semibold hover:bg-background/10"
            >
              Delete
            </button>
            <button
              type="button"
              onClick={clearSelection}
              className="ml-1 cursor-pointer text-[18px] leading-none text-background/70 hover:text-background"
              aria-label="Clear selection"
            >
              ×
            </button>
          </div>
        </div>
      )}

    </div>
  );
}

const PLUGIN_INSTALL_COMMANDS = "uv tool install stashai\nstash signin";

// Empty state that sells the plugin: sessions arrive via the agent hooks the
// CLI installs, so an empty list usually means that setup hasn't happened yet.
function SessionsEmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted-foreground">
      <p className="m-0">No sessions yet.</p>
      <p className="m-0 mt-1.5">
        Sessions from Claude Code, Cursor, Codex and other agents appear here
        automatically once the Stash plugin is installed.
      </p>
      <div className="mt-3">
        <CopyableCommandBlock commands={PLUGIN_INSTALL_COMMANDS} />
      </div>
    </div>
  );
}

function SessionsView({
  view,
  sessions,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
}: {
  view: ViewKey;
  sessions: SessionSummary[];
  isPinned: (sessionId: string) => boolean;
  onTogglePin: (sessionId: string) => void;
  selectedIds: Set<string>;
  onToggleSelect: (sessionId: string) => void;
}) {
  if (sessions.length === 0) {
    return <SessionsEmptyState />;
  }

  if (view === "list") {
    return (
      <SessionsTable
        sessions={sessions}
        isPinned={isPinned}
        onTogglePin={onTogglePin}
        selectedIds={selectedIds}
        onToggleSelect={onToggleSelect}
      />
    );
  }

  if (view === "day") {
    const groups = groupSessionsByDayAndUser(sessions);
    return (
      <div className="flex flex-col gap-4">
        {groups.map((group, i) => (
          <DayGroup
            key={group.key}
            group={group}
            initialOpen={i === 0}
            isPinned={isPinned}
            onTogglePin={onTogglePin}
            selectedIds={selectedIds}
            onToggleSelect={onToggleSelect}
          />
        ))}
      </div>
    );
  }

  const groups =
    view === "user" ? groupSessionsByUser(sessions) : groupSessionsByAgent(sessions);
  return (
    <div className="flex flex-col gap-4">
      {groups.map((group, i) => (
        <FlatGroup
          key={group.key}
          group={group}
          initialOpen={i === 0}
          isPinned={isPinned}
          onTogglePin={onTogglePin}
          selectedIds={selectedIds}
          onToggleSelect={onToggleSelect}
        />
      ))}
    </div>
  );
}

function DayGroup({
  group,
  initialOpen,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
}: {
  group: SessionDayGroup;
  initialOpen: boolean;
  isPinned: (sessionId: string) => boolean;
  onTogglePin: (sessionId: string) => void;
  selectedIds: Set<string>;
  onToggleSelect: (sessionId: string) => void;
}) {
  const [open, setOpen] = useState(initialOpen);
  return (
    <section>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-raised"
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
              <div className="mb-1 px-2 text-[11px] font-medium text-muted-foreground">{bucket.user}</div>
              <SessionsTable
                sessions={bucket.sessions}
                isPinned={isPinned}
                onTogglePin={onTogglePin}
                selectedIds={selectedIds}
                onToggleSelect={onToggleSelect}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function FlatGroup({
  group,
  initialOpen,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
}: {
  group: SessionFlatGroup;
  initialOpen: boolean;
  isPinned: (sessionId: string) => boolean;
  onTogglePin: (sessionId: string) => void;
  selectedIds: Set<string>;
  onToggleSelect: (sessionId: string) => void;
}) {
  const [open, setOpen] = useState(initialOpen);
  return (
    <section>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-raised"
      >
        <Chev open={open} />
        <h2 className="m-0 font-display text-[15px] font-semibold">{group.label}</h2>
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {group.count}
        </span>
      </button>
      {open && (
        <div className="mt-1.5">
          <SessionsTable
            sessions={group.sessions}
            isPinned={isPinned}
            onTogglePin={onTogglePin}
            selectedIds={selectedIds}
            onToggleSelect={onToggleSelect}
          />
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
      <div className="inline-flex gap-1 rounded-full border border-border bg-surface/60 p-1 shadow-sm">
        {options.map((opt) => {
          const active = value === opt.key;
          return (
            <button
              key={opt.key}
              type="button"
              onClick={() => onChange(opt.key)}
              className={
                "cursor-pointer rounded-full px-2.5 py-1 text-[12px] leading-none transition-colors " +
                (active
                  ? "bg-base font-semibold text-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-raised/70 hover:text-foreground")
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
      className={"h-3 w-3 text-muted-foreground transition-transform " + (open ? "rotate-90" : "")}
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
  sessions,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
}: {
  sessions: SessionSummary[];
  isPinned: (sessionId: string) => boolean;
  onTogglePin: (sessionId: string) => void;
  selectedIds: Set<string>;
  onToggleSelect: (sessionId: string) => void;
}) {
  if (sessions.length === 0) {
    return <SessionsEmptyState />;
  }

  // Folders are the legacy filing lane, written only by installed clients'
  // API calls. The column appears only when something here is actually filed,
  // so accounts that never used folders keep the plain layout.
  const showFolder = sessions.some((s) => s.session_folder_name);

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      <div
        className={
          "hidden gap-3 border-b border-border bg-base/70 px-3 py-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground md:grid " +
          (showFolder ? GRID_COLS_WITH_FOLDER : GRID_COLS)
        }
      >
        <span>User</span>
        <span>Session</span>
        {showFolder && <span>Folder</span>}
        <span>Events</span>
        <span>Agent</span>
        <span>Date</span>
        <span>Updated</span>
        <span />
      </div>
      {sessions.map((session) => (
        <SessionTableRow
          key={session.session_id}
          session={session}
          showFolder={showFolder}
          pinned={isPinned(session.session_id)}
          onTogglePin={onTogglePin}
          selected={selectedIds.has(session.session_id)}
          onToggleSelect={onToggleSelect}
        />
      ))}
    </div>
  );
}

const GRID_COLS =
  "md:grid-cols-[minmax(128px,0.68fr)_minmax(240px,1.7fr)_58px_minmax(104px,0.62fr)_94px_88px_28px]";
const GRID_COLS_WITH_FOLDER =
  "md:grid-cols-[minmax(128px,0.68fr)_minmax(200px,1.4fr)_minmax(110px,0.6fr)_58px_minmax(104px,0.62fr)_94px_88px_28px]";

function SessionTableRow({
  session,
  showFolder,
  pinned,
  onTogglePin,
  selected,
  onToggleSelect,
}: {
  session: SessionSummary;
  showFolder: boolean;
  pinned: boolean;
  onTogglePin: (sessionId: string) => void;
  selected: boolean;
  onToggleSelect: (sessionId: string) => void;
}) {
  const user = requireSessionUserName(session.user_name);
  const agent = session.agent_name || "agent";
  const avatar = avatarFor(user);

  return (
    <Link
      href={`/sessions/${encodeURIComponent(session.session_id)}`}
      className={
        "group/srow grid min-h-12 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-3 py-2 text-[13px] last:border-b-0 " +
        (showFolder ? GRID_COLS_WITH_FOLDER : GRID_COLS) +
        " " +
        (selected ? "bg-[var(--color-brand-50)]" : "hover:bg-[var(--color-brand-50)]")
      }
    >
      <div className="hidden min-w-0 items-center gap-2 md:flex">
        <SelectBox
          selected={selected}
          onToggle={() => onToggleSelect(session.session_id)}
        />
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
        <div className="flex min-w-0 items-center gap-2">
          <div className="min-w-0 flex-1 truncate font-medium text-foreground">{sessionTitle(session)}</div>
        </div>
        <div className="mt-0.5 truncate text-[11px] text-muted-foreground md:hidden">
          {[
            user,
            session.session_folder_name,
            agent,
            formatRelative(session.last_event_at),
          ]
            .filter(Boolean)
            .join(", ")}
        </div>
      </div>
      {showFolder && (
        <span className="hidden truncate text-[12px] text-muted-foreground md:block">
          {session.session_folder_name ?? "—"}
        </span>
      )}
      <span className="hidden items-center gap-1 text-[12px] text-muted-foreground md:flex">
        <MessageIcon />
        {session.event_count}
      </span>
      <span className="hidden truncate text-muted-foreground md:block">{agent}</span>
      <span className="hidden whitespace-nowrap text-[12px] text-muted-foreground md:block">
        {formatDate(session.last_event_at || session.started_at)}
      </span>
      <span className="justify-self-end whitespace-nowrap text-[12px] text-muted-foreground">
        {formatRelative(session.last_event_at)}
      </span>
      <span
        role="button"
        tabIndex={0}
        aria-label={pinned ? "Unpin session" : "Pin session"}
        aria-pressed={pinned}
        title={pinned ? "Unpin" : "Pin"}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onTogglePin(session.session_id);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            onTogglePin(session.session_id);
          }
        }}
        className={
          "hidden cursor-pointer justify-self-end rounded p-1 transition hover:bg-raised md:block " +
          (pinned
            ? "text-[var(--color-brand-600)] hover:text-[var(--color-brand-700)]"
            : "text-muted-foreground/40 hover:text-foreground")
        }
      >
        <PinIcon className="text-[15px]" />
      </span>
    </Link>
  );
}

function sessionTitle(s: SessionSummary): string {
  const title = s.title.trim().replace(/\s+/g, " ");
  return title.length > 96 ? title.slice(0, 96) + "…" : title;
}

function sessionTime(session: SessionSummary): number {
  const time = new Date(session.last_event_at || session.started_at).getTime();
  return Number.isNaN(time) ? 0 : time;
}

const AVATAR_PALETTE: { bg: string; fg: string }[] = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-orange-200", fg: "text-orange-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-teal-200", fg: "text-teal-800" },
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


