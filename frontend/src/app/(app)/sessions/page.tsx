"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import CopyableCommandBlock from "@/components/CopyableCommandBlock";
import CustomSelect from "@/components/CustomSelect";
import SessionUpload from "@/components/SessionUpload";
import { SessionsListSkeleton } from "@/components/SkeletonStates";
import { FolderIcon, PinIcon } from "@/components/SkillIcons";
import { SelectBox } from "@/components/content/file-browser/ItemsList";
import { useAuth } from "@/hooks/useAuth";
import {
  assignSessionFolder,
  createSessionFolder,
  deleteSession,
  deleteSessionFolder,
  displayVisibility,
  listMySessions,
  listSessionFolders,
  listSharedSessionFolderSessions,
  listSharedWithMe,
  type DisplayVisibility,
  type SessionFolder,
  type SessionSummary,
  type SharedWithMeItem,
} from "@/lib/api";
import SessionFolderShareModal from "@/components/share/SessionFolderShareModal";
import { usePins } from "@/lib/pins";
import {
  groupSessionsByAgent,
  groupSessionsByDayAndUser,
  groupSessionsByFolder,
  groupSessionsByLinearTicket,
  groupSessionsByUser,
  requireSessionUserName,
  type SessionDayGroup,
  type SessionFlatGroup,
} from "@/lib/sessionGrouping";

type ViewKey = "list" | "day" | "user" | "agent" | "ticket" | "folder";
type SortColumn = "updated" | "events" | "name" | "agent";
type SortKey = { column: SortColumn; dir: "asc" | "desc" };

// Each column's first click picks the order you almost always want first:
// newest, busiest, A-Z. Clicking the active column flips it.
const FIRST_DIR: Record<SortColumn, "asc" | "desc"> = {
  updated: "desc",
  events: "desc",
  name: "asc",
  agent: "asc",
};

const VIEW_STORAGE_KEY = "stash_sessions_view";

// One folder page. Drilled-in folders fetch this many at a time and load more
// on scroll, so folders with thousands of sessions stay fully reachable.
const SESSIONS_PAGE_SIZE = 100;

const VIEWS: { key: ViewKey; label: string }[] = [
  { key: "list", label: "List" },
  { key: "day", label: "By day" },
  { key: "user", label: "By user" },
  { key: "agent", label: "By agent" },
  { key: "ticket", label: "By ticket" },
  { key: "folder", label: "By folder" },
];

// Drag payload: the DB row ids (sessions.id) of the dragged sessions. Dragging
// a selected row carries the whole selection, like the file browser.
const SESSION_DRAG_MIME = "application/x-skill-sessions";

// Drag wiring threaded down to session rows: whether rows can be dragged at
// all (off inside shared folders), the row ids the current selection would
// carry, and a signal so drop targets can reveal themselves mid-drag.
interface SessionDrag {
  canDrag: boolean;
  selectedRowIds: string[];
  onActiveChange: (active: boolean) => void;
}

const NO_DRAG: SessionDrag = {
  canDrag: false,
  selectedRowIds: [],
  onActiveChange: () => {},
};

function readSessionDrop(e: DragEvent<HTMLElement>): string[] {
  const raw = e.dataTransfer.getData(SESSION_DRAG_MIME);
  if (!raw) return [];
  try {
    const ids = JSON.parse(raw);
    return Array.isArray(ids) ? ids.filter((id) => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export default function SkillSessionsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const pins = usePins("sessions");
  const confirm = useConfirm();

  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [folders, setFolders] = useState<SessionFolder[]>([]);
  const [sharedFolders, setSharedFolders] = useState<SharedWithMeItem[]>([]);
  const [openFolder, setOpenFolder] = useState<OpenFolder | null>(null);
  // Bumped after a move/assign so a drilled-in folder refetches its own
  // sessions — its list is fetched independently of the global recent window.
  const [drillRefresh, setDrillRefresh] = useState(0);
  const [shareFolder, setShareFolder] = useState<SessionFolder | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<ViewKey>("list");
  const [sort, setSort] = useState<SortKey>({ column: "updated", dir: "desc" });
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [dragActive, setDragActive] = useState(false);

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
      const [list, folderList, sharedAll] = await Promise.all([
        listMySessions(200),
        listSessionFolders().catch(() => [] as SessionFolder[]),
        listSharedWithMe().catch(() => [] as SharedWithMeItem[]),
      ]);
      setSessions(list);
      setFolders(folderList);
      setSharedFolders(sharedAll.filter((i) => i.object_type === "session_folder"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sessions");
    }
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const sorted = useMemo(() => {
    if (!sessions) return null;
    return sortSessions(sessions, sort);
  }, [sessions, sort]);

  if (loading) return <SessionsListSkeleton />;
  if (!user) return null;
  if (sorted === null) return <SessionsListSkeleton />;

  const pinnedSessions = (sorted ?? []).filter((s) =>
    pins.pinnedSet.has(s.session_id),
  );
  const selectedSessions = (sorted ?? []).filter((s) =>
    selectedIds.has(s.session_id),
  );
  const drag: SessionDrag = {
    canDrag: true,
    selectedRowIds: selectedSessions
      .filter((s) => s.id)
      .map((s) => s.id!),
    onActiveChange: setDragActive,
  };

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

  // Move the selected sessions into a folder (or out of one, with folderId
  // null). `__new__` prompts for a folder name and creates it first.
  async function moveSelectedToFolder(folderId: string | null) {
    const targets = selectedSessions.filter((s) => s.id);
    if (targets.length === 0) return;
    let destination = folderId;
    if (folderId === "__new__") {
      const name = window.prompt("New folder name")?.trim();
      if (!name) return;
      try {
        destination = (await createSessionFolder(name)).id;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not create folder");
        return;
      }
    }
    try {
      await assignSessionFolder(
        targets.map((s) => s.id!),
        destination,
      );
      clearSelection();
      await load();
      setDrillRefresh((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not move sessions");
    }
  }

  // Drop handler: move the dragged session row ids into a folder.
  async function moveRowsToFolder(rowIds: string[], folderId: string) {
    if (rowIds.length === 0) return;
    try {
      await assignSessionFolder(rowIds, folderId);
      clearSelection();
      await load();
      setDrillRefresh((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not move sessions");
    }
  }

  async function newFolder() {
    const name = window.prompt("New folder name")?.trim();
    if (!name) return;
    try {
      await createSessionFolder(name);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create folder");
    }
  }

  async function removeFolder(folder: SessionFolder) {
    const ok = await confirm({
      title: `Delete folder "${folder.name}"?`,
      body: "Sessions inside become unfiled (not deleted).",
      confirmLabel: "Delete",
    });
    if (!ok) return;
    try {
      await deleteSessionFolder(folder.id);
      setOpenFolder(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete folder");
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


        {pinnedSessions.length > 0 && (
          <section className="mb-5">
            <h2 className="m-0 mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <PinIcon className="text-[13px]" />
              Pinned
            </h2>
            <SessionsTable
              sessions={pinnedSessions}
              sort={sort}
              onSort={setSort}
              isPinned={pins.isPinned}
              onTogglePin={pins.toggle}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
              drag={drag}
            />
          </section>
        )}

        {/* Sessions-first: the landing is every session, flat, because the tab
            exists to let you look at your sessions. Folders organise them and
            sit below; the VFS view is where sessions nest into directories. */}
        <FolderDrill
            folder={openFolder ?? ALL_SESSIONS}
            refreshKey={drillRefresh}
            folders={folders}
            view={view}
            sort={sort}
            onBack={() => setOpenFolder(null)}
            onChangeView={setViewPersisted}
            onChangeSort={setSort}
            onShare={(f) => setShareFolder(f)}
            onDelete={removeFolder}
            isPinned={pins.isPinned}
            onTogglePin={pins.toggle}
            selectedIds={selectedIds}
            onToggleSelect={toggleSelect}
            drag={drag}
            dragActive={dragActive}
            onDropSessions={moveRowsToFolder}
            onUploaded={load}
          />
        {!openFolder && (
          <div className="mt-8 border-t border-border pt-5">
            <FoldersSection
              ownFolders={folders}
              sharedFolders={sharedFolders}
              onOpen={setOpenFolder}
              onNewFolder={newFolder}
              onShare={(f) => setShareFolder(f)}
              onDropSessions={moveRowsToFolder}
            />
          </div>
        )}
      </div>

      {selectedSessions.length > 0 && (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center">
          <div className="pointer-events-auto flex items-center gap-3 rounded-lg border border-border bg-foreground px-4 py-2 text-[13px] text-background shadow-lg">
            <span className="font-medium">{selectedSessions.length} selected</span>
            <select
              aria-label="Move to folder"
              value=""
              onChange={(e) => {
                const v = e.target.value;
                if (v) void moveSelectedToFolder(v === "__none__" ? null : v);
                e.target.value = "";
              }}
              className="rounded-md border border-background/40 bg-foreground px-2 py-0.5 text-[12px] font-semibold text-background hover:bg-background/10"
            >
              <option value="">Move to folder…</option>
              <option value="__new__">+ New folder</option>
              {folders.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
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

      {shareFolder && (
        <SessionFolderShareModal
          folder={shareFolder}
          onClose={() => setShareFolder(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}

const PLUGIN_INSTALL_COMMANDS = "uv tool install stashai\nstash signin";

// Empty state that sells the plugin: sessions arrive via the agent hooks the
// CLI installs, so an empty list usually means that setup hasn't happened yet.
// Shared folders skip the CTA — their sessions come from the folder's owner.
function SessionsEmptyState({ withInstallCta }: { withInstallCta: boolean }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted-foreground">
      <p className="m-0">No sessions yet.</p>
      {withInstallCta && (
        <>
          <p className="m-0 mt-1.5">
            Sessions from Claude Code, Cursor, Codex and other agents appear here
            automatically once the Stash plugin is installed.
          </p>
          <div className="mt-3">
            <CopyableCommandBlock commands={PLUGIN_INSTALL_COMMANDS} />
          </div>
        </>
      )}
    </div>
  );
}

function SessionsView({
  view,
  sessions,
  folders,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
  drag,
  withInstallCta,
  sort,
  onSort,
}: {
  view: ViewKey;
  sessions: SessionSummary[];
  folders: SessionFolder[];
  sort: SortKey;
  onSort: (s: SortKey) => void;
  isPinned: (sessionId: string) => boolean;
  onTogglePin: (sessionId: string) => void;
  selectedIds: Set<string>;
  onToggleSelect: (sessionId: string) => void;
  drag: SessionDrag;
  withInstallCta: boolean;
}) {
  if (sessions.length === 0) {
    return <SessionsEmptyState withInstallCta={withInstallCta} />;
  }

  if (view === "list") {
    return (
      <SessionsTable
        sessions={sessions}
        sort={sort}
        onSort={onSort}
        isPinned={isPinned}
        onTogglePin={onTogglePin}
        selectedIds={selectedIds}
        onToggleSelect={onToggleSelect}
        drag={drag}
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
            sort={sort}
            onSort={onSort}
            initialOpen={i === 0}
            isPinned={isPinned}
            onTogglePin={onTogglePin}
            selectedIds={selectedIds}
            onToggleSelect={onToggleSelect}
            drag={drag}
          />
        ))}
      </div>
    );
  }

  const groups =
    view === "user"
      ? groupSessionsByUser(sessions)
      : view === "ticket"
      ? groupSessionsByLinearTicket(sessions)
      : view === "folder"
      ? groupSessionsByFolder(sessions, folders)
      : groupSessionsByAgent(sessions);
  return (
    <div className="flex flex-col gap-4">
      {groups.map((group, i) => (
        <FlatGroup
          key={group.key}
          group={group}
          sort={sort}
          onSort={onSort}
          soleGroup={groups.length === 1}
          initialOpen={i === 0}
          isPinned={isPinned}
          onTogglePin={onTogglePin}
          selectedIds={selectedIds}
          onToggleSelect={onToggleSelect}
          drag={drag}
        />
      ))}
    </div>
  );
}

function DayGroup({
  group,
  sort,
  onSort,
  initialOpen,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
  drag,
}: {
  group: SessionDayGroup;
  sort: SortKey;
  onSort: (s: SortKey) => void;
  initialOpen: boolean;
  isPinned: (sessionId: string) => boolean;
  onTogglePin: (sessionId: string) => void;
  selectedIds: Set<string>;
  onToggleSelect: (sessionId: string) => void;
  drag: SessionDrag;
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
                sort={sort}
                onSort={onSort}
                isPinned={isPinned}
                onTogglePin={onTogglePin}
                selectedIds={selectedIds}
                onToggleSelect={onToggleSelect}
                drag={drag}
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
  sort,
  onSort,
  soleGroup,
  initialOpen,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
  drag,
}: {
  group: SessionFlatGroup;
  sort: SortKey;
  onSort: (s: SortKey) => void;
  soleGroup: boolean;
  initialOpen: boolean;
  isPinned: (sessionId: string) => boolean;
  onTogglePin: (sessionId: string) => void;
  selectedIds: Set<string>;
  onToggleSelect: (sessionId: string) => void;
  drag: SessionDrag;
}) {
  const [open, setOpen] = useState(initialOpen);
  return (
    <section>
      {/* Grouping that yields one group is not grouping — drawing "Unlabeled 7"
          over the whole list only adds a lid to it. */}
      {!soleGroup && (
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
      )}
      {(open || soleGroup) && (
        <div className="mt-1.5">
          <SessionsTable
            sessions={group.sessions}
            sort={sort}
            onSort={onSort}
            isPinned={isPinned}
            onTogglePin={onTogglePin}
            selectedIds={selectedIds}
            onToggleSelect={onToggleSelect}
            drag={drag}
          />
        </div>
      )}
    </section>
  );
}

function GroupBySelect({
  value,
  onChange,
}: {
  value: ViewKey;
  onChange: (v: ViewKey) => void;
}) {
  return (
    <span className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
      Group
      <CustomSelect
        value={value}
        onChange={(v) => onChange(v as ViewKey)}
        ariaLabel="Group sessions by"
        align="right"
        options={VIEWS.map((v) => ({
          value: v.key,
          label: v.key === "list" ? "None" : v.label.slice(3, 4).toUpperCase() + v.label.slice(4),
        }))}
        className="cursor-pointer rounded-md border border-border bg-transparent px-2 py-1 text-[12.5px] text-foreground hover:bg-raised"
      />
    </span>
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
  sort,
  onSort,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
  drag = NO_DRAG,
}: {
  sessions: SessionSummary[];
  sort: SortKey;
  onSort: (s: SortKey) => void;
  isPinned: (sessionId: string) => boolean;
  onTogglePin: (sessionId: string) => void;
  selectedIds: Set<string>;
  onToggleSelect: (sessionId: string) => void;
  drag?: SessionDrag;
}) {
  if (sessions.length === 0) {
    return <SessionsEmptyState withInstallCta />;
  }

  // A column that never varies is not a column, it is a watermark: User is the
  // same name on every row in a personal stash, and Ticket is empty until
  // something links one. Both earn their place per listing, not globally.
  const showUser = new Set(sessions.map((s) => s.user_name)).size > 1;
  const showTicket = sessions.some((s) => primaryTicket(s) !== null);
  const cols = gridColumns(showUser, showTicket);

  return (
    <div>
      <div
        className="hidden gap-3 border-b border-border px-3 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground md:grid"
        style={{ gridTemplateColumns: cols }}
      >
        {showUser && <span>User</span>}
        <SessionSortHeader label="Session" column="name" sort={sort} onSort={onSort} />
        {showTicket && <span>Ticket</span>}
        <SessionSortHeader label="Events" column="events" sort={sort} onSort={onSort} />
        <SessionSortHeader label="Agent" column="agent" sort={sort} onSort={onSort} />
        <SessionSortHeader label="Updated" column="updated" sort={sort} onSort={onSort} />
        <span />
      </div>
      {sessions.map((session) => (
        <SessionTableRow
          key={session.session_id}
          session={session}
          cols={cols}
          showUser={showUser}
          showTicket={showTicket}
          pinned={isPinned(session.session_id)}
          onTogglePin={onTogglePin}
          selected={selectedIds.has(session.session_id)}
          onToggleSelect={onToggleSelect}
          drag={drag}
        />
      ))}
    </div>
  );
}

/** Columns collapse out of the template entirely when they carry nothing, so
 *  the remaining ones take the space instead of leaving a gap. */
function gridColumns(showUser: boolean, showTicket: boolean): string {
  return [
    showUser ? "minmax(120px,0.6fr)" : null,
    "minmax(240px,2fr)",
    showTicket ? "86px" : null,
    "58px",
    "minmax(96px,0.55fr)",
    "88px",
    "28px",
  ]
    .filter(Boolean)
    .join(" ");
}

// Sorting lives in the column headers, where a table keeps it. Updated toggles
// between newest and oldest; the others are one-way orders.
function SessionSortHeader({
  label,
  column,
  sort,
  onSort,
}: {
  label: string;
  column: SortColumn;
  sort: SortKey;
  onSort: (s: SortKey) => void;
}) {
  const active = sort.column === column;
  return (
    <button
      type="button"
      onClick={() =>
        onSort({
          column,
          dir: active ? (sort.dir === "asc" ? "desc" : "asc") : FIRST_DIR[column],
        })
      }
      className={
        "flex cursor-pointer items-center gap-1 text-left text-[11px] font-medium uppercase tracking-[0.08em] hover:text-foreground " +
        (active ? "text-foreground" : "text-muted-foreground")
      }
    >
      {label}
      {active && <span aria-hidden>{sort.dir === "asc" ? "\u25B2" : "\u25BC"}</span>}
    </button>
  );
}

function SessionTableRow({
  session,
  cols,
  showUser,
  showTicket,
  pinned,
  onTogglePin,
  selected,
  onToggleSelect,
  drag,
}: {
  session: SessionSummary;
  cols: string;
  showUser: boolean;
  showTicket: boolean;
  pinned: boolean;
  onTogglePin: (sessionId: string) => void;
  selected: boolean;
  onToggleSelect: (sessionId: string) => void;
  drag: SessionDrag;
}) {
  const user = requireSessionUserName(session.user_name);
  const agent = session.agent_name || "agent";
  const avatar = avatarFor(user);
  const ticket = primaryTicket(session);

  return (
    <Link
      href={`/sessions/${encodeURIComponent(session.session_id)}`}
      draggable={drag.canDrag && !!session.id}
      onDragStart={(e: DragEvent<HTMLAnchorElement>) => {
        if (!session.id) return;
        const ids =
          selected && drag.selectedRowIds.length > 1
            ? drag.selectedRowIds
            : [session.id];
        e.dataTransfer.setData(SESSION_DRAG_MIME, JSON.stringify(ids));
        e.dataTransfer.effectAllowed = "move";
        drag.onActiveChange(true);
      }}
      onDragEnd={() => drag.onActiveChange(false)}
      className={
        "group/srow grid min-h-10 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border-subtle px-3 py-1.5 text-[13px] last:border-b-0 md:grid " +
        (selected ? "bg-[var(--color-brand-50)]" : "hover:bg-[var(--color-brand-50)]/60")
      }
      style={{ gridTemplateColumns: cols }}
    >
      <div className={"min-w-0 items-center gap-2 " + (showUser ? "hidden md:flex" : "hidden")}>
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
          <SelectBox
            selected={selected}
            onToggle={() => onToggleSelect(session.session_id)}
          />
          <div className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-foreground">{sessionTitle(session)}</div>
          {ticket && (
            <span className="md:hidden">
              <LinearTicketPill ticket={ticket} compact />
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate text-[11px] text-muted-foreground md:hidden">
          {[user, ticket?.ticket_identifier, agent, formatRelative(session.last_event_at)]
            .filter(Boolean)
            .join(", ")}
        </div>
      </div>
      {showTicket && (
        <span className="hidden min-w-0 md:block">
          {ticket ? (
            <LinearTicketPill ticket={ticket} />
          ) : (
            <span className="text-[12px] text-muted-foreground/40">—</span>
          )}
        </span>
      )}
      <span className="hidden items-center gap-1 text-[12px] text-muted-foreground md:flex">
        <MessageIcon />
        {session.event_count}
      </span>
      <span className="hidden truncate text-[12px] text-muted-foreground md:block">{agent}</span>
      <span
        className="justify-self-end whitespace-nowrap text-[12px] text-muted-foreground"
        title={formatDate(session.last_event_at || session.started_at)}
      >
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

function primaryTicket(session: SessionSummary) {
  return session.linear_tickets[0] ?? null;
}

function LinearTicketPill({
  ticket,
  compact = false,
}: {
  ticket: NonNullable<ReturnType<typeof primaryTicket>>;
  compact?: boolean;
}) {
  return (
    <span
      className={
        "inline-flex max-w-full shrink-0 items-center rounded border border-[var(--color-brand-200)] bg-[var(--color-brand-50)] font-mono font-semibold text-[var(--color-brand-700)] " +
        (compact ? "px-1.5 py-0 text-[10px]" : "px-2 py-0.5 text-[11px]")
      }
      title={ticket.ticket_title || ticket.ticket_identifier}
    >
      {ticket.ticket_identifier}
    </span>
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
  // "Aug 4", not "8/4/2026": one column should not switch numbering systems
  // partway down. The exact timestamp is on the row's title attribute.
  return formatDate(iso);
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

// --- Session folders as navigable "vaults" (own + shared-with-me) ---

// `folder` is the full record for own folders (enables Share/Delete + access
// badge); shared-with-me folders only carry the id/name.
type OpenFolder = {
  /** null = every session in the scope: the tab's flat landing view. Folders
   *  are a way to organise sessions, not a wall you must click through to see
   *  them. */
  id: string | null;
  name: string;
  shared: boolean;
  folder?: SessionFolder;
};

const ALL_SESSIONS: OpenFolder = { id: null, name: "All sessions", shared: false };

const VIS_DOT: Record<DisplayVisibility, string> = {
  public: "#22C55E",
  shared: "var(--color-brand-500)",
  private: "#9CA3AF",
};

// Private folders show no badge (the common, quiet case); Shared/Public stand out.
function FolderAccessBadge({ folder }: { folder: SessionFolder }) {
  const vis = displayVisibility(folder.access, folder.share_count);
  if (vis === "private") return null;
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
      <span
        className="inline-block h-[7px] w-[7px] rounded-full"
        style={{ background: VIS_DOT[vis] }}
      />
      {vis === "shared" ? `Shared: ${folder.share_count}` : "Public"}
    </span>
  );
}

function FoldersSection({
  ownFolders,
  sharedFolders,
  onOpen,
  onNewFolder,
  onShare,
  onDropSessions,
}: {
  ownFolders: SessionFolder[];
  sharedFolders: SharedWithMeItem[];
  onOpen: (f: OpenFolder) => void;
  onNewFolder: () => void;
  onShare: (f: SessionFolder) => void;
  onDropSessions: (rowIds: string[], folderId: string) => void;
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between border-b border-border pb-2.5">
        <h2 className="m-0 font-display text-[15px] font-semibold text-foreground">Folders</h2>
        <button
          type="button"
          onClick={onNewFolder}
          className="cursor-pointer rounded-md border border-border bg-base px-2.5 py-1 text-[12.5px] font-medium text-foreground hover:bg-raised"
        >
          + New folder
        </button>
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {ownFolders.map((f) => (
          <FolderCard
            key={f.id}
            folder={f}
            onClick={() => onOpen({ id: f.id, name: f.name, shared: false, folder: f })}
            onShare={() => onShare(f)}
            onDropSessions={(rowIds) => onDropSessions(rowIds, f.id)}
          />
        ))}
        {sharedFolders.map((f) => (
          <SharedFolderCard
            key={f.object_id}
            name={f.name}
            subtitle={f.shared_by ? `shared by ${f.shared_by}` : "shared with you"}
            onClick={() => onOpen({ id: f.object_id, name: f.name, shared: true })}
          />
        ))}
      </div>
    </section>
  );
}

function FolderCard({
  folder,
  onClick,
  onShare,
  onDropSessions,
}: {
  folder: SessionFolder;
  onClick: () => void;
  onShare: () => void;
  onDropSessions: (rowIds: string[]) => void;
}) {
  const [over, setOver] = useState(false);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes(SESSION_DRAG_MIME)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false);
        const rowIds = readSessionDrop(e);
        if (rowIds.length === 0) return;
        e.preventDefault();
        onDropSessions(rowIds);
      }}
      className={
        "group flex cursor-pointer items-start gap-2.5 rounded-lg border bg-surface/50 px-3 py-3 text-left transition hover:border-[var(--color-brand-300)] hover:bg-raised/50 " +
        (over ? "border-[var(--color-brand-300)] ring-1 ring-inset ring-[var(--color-brand-300)]" : "border-border")
      }
    >
      <span aria-hidden className="mt-0.5 text-muted-foreground">
        <FolderIcon />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="min-w-0 truncate text-[13.5px] font-semibold text-foreground">
            {folder.name}
          </span>
          {folder.is_default && (
            <span className="shrink-0 rounded-full border border-border bg-base px-1.5 py-px text-[9.5px] uppercase tracking-wide text-muted-foreground">
              Default
            </span>
          )}
        </span>
        <span className="mt-1 flex items-center gap-2">
          <span className="text-[11.5px] text-muted-foreground">
            {folder.session_count} session{folder.session_count === 1 ? "" : "s"}
          </span>
          {displayVisibility(folder.access, folder.share_count) !== "private" && (
            <>
              <FolderAccessBadge folder={folder} />
            </>
          )}
        </span>
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onShare();
        }}
        className="shrink-0 cursor-pointer rounded-md px-2 py-0.5 text-[11.5px] font-medium text-muted-foreground opacity-0 transition group-hover:opacity-100 hover:bg-base hover:text-foreground"
      >
        Share
      </button>
    </div>
  );
}

function SharedFolderCard({
  name,
  subtitle,
  onClick,
}: {
  name: string;
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border bg-surface/50 px-3 py-3 text-left transition hover:border-[var(--color-brand-300)] hover:bg-raised/50"
    >
      <span aria-hidden className="mt-0.5 text-muted-foreground">
        <FolderIcon />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[13.5px] font-semibold text-foreground">{name}</span>
        <span className="block truncate text-[11.5px] text-muted-foreground">{subtitle}</span>
      </span>
    </button>
  );
}

function FolderDrill({
  folder,
  refreshKey,
  folders,
  view,
  sort,
  onBack,
  onChangeView,
  onChangeSort,
  onShare,
  onDelete,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
  drag,
  dragActive,
  onDropSessions,
  onUploaded,
}: {
  folder: OpenFolder;
  refreshKey: number;
  folders: SessionFolder[];
  view: ViewKey;
  sort: SortKey;
  onBack: () => void;
  onChangeView: (v: ViewKey) => void;
  onChangeSort: (s: SortKey) => void;
  onShare: (f: SessionFolder) => void;
  onDelete: (f: SessionFolder) => void;
  isPinned: (sessionId: string) => boolean;
  onTogglePin: (sessionId: string) => void;
  selectedIds: Set<string>;
  onToggleSelect: (sessionId: string) => void;
  drag: SessionDrag;
  dragActive: boolean;
  onDropSessions: (rowIds: string[], folderId: string) => void;
  onUploaded: () => void;
}) {
  const [folderSessions, setFolderSessions] = useState<SessionSummary[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  // Always fetch the folder's own sessions from the backend. The global recent
  // window the landing page loads can miss a folder's older sessions entirely,
  // so a folder-scoped query is the only thing that reliably fills the drill.
  // Shared folders load in full from their own endpoint; own folders page
  // through /me/sessions, so they need infinite scroll past the first page.
  useEffect(() => {
    setFolderSessions(null);
    setHasMore(false);
    const request =
      folder.shared && folder.id
        ? listSharedSessionFolderSessions(folder.id)
        : listMySessions(SESSIONS_PAGE_SIZE, folder.id ?? undefined, 0);
    request
      .then((rows) => {
        setFolderSessions(rows);
        setHasMore(!folder.shared && rows.length === SESSIONS_PAGE_SIZE);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load sessions"));
  }, [folder, refreshKey]);

  const loadMore = useCallback(async () => {
    if (folder.shared || loadingMore || !hasMore || folderSessions === null) return;
    setLoadingMore(true);
    try {
      const rows = await listMySessions(
        SESSIONS_PAGE_SIZE,
        folder.id ?? undefined,
        folderSessions.length
      );
      setFolderSessions((prev) => [...(prev ?? []), ...rows]);
      setHasMore(rows.length === SESSIONS_PAGE_SIZE);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load more sessions");
    } finally {
      setLoadingMore(false);
    }
  }, [folder, loadingMore, hasMore, folderSessions]);

  // Auto-load the next page when the sentinel scrolls into view; the button it
  // wraps is the manual fallback if the observer can't fire. Pagination follows
  // the server's recent-first order, so only the "recent" sort places new pages
  // below the sentinel. Other sorts reorder appended pages above it, which would
  // keep the sentinel in view and cascade-load the whole folder — for those the
  // button stays as the one-page-at-a-time control.
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = sentinelRef.current;
    // Newest-first is the server's own paging order, so appended pages land
    // below the sentinel. Any other order would place them above it and
    // cascade-load the whole folder.
    if (!el || !hasMore || sort.column !== "updated" || sort.dir !== "desc") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore();
      },
      { rootMargin: "600px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loadMore, sort]);

  const ownFolder = folder.folder;
  // Shared folders are read-only: render the same chronological browser, but
  // without selection (no move/delete on sessions you don't own).
  const drillSessions = sortSessions(folderSessions ?? [], sort);

  const isAll = folder.id === null;

  return (
    <div>
      {!isAll && (
        <button
          type="button"
          onClick={onBack}
          className="mb-3 inline-flex cursor-pointer items-center gap-1 text-[12.5px] text-muted-foreground hover:text-foreground"
        >
          ← All folders
        </button>
      )}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="m-0 flex items-baseline gap-2 font-display text-[18px] font-semibold text-foreground">
          {!isAll && (
            <span aria-hidden className="text-muted-foreground">
              <FolderIcon />
            </span>
          )}
          {isAll ? "Sessions" : folder.name}
          {folderSessions !== null && (
            <span className="text-[13px] font-normal text-muted-foreground">
              {folderSessions.length}
            </span>
          )}
          {ownFolder && <FolderAccessBadge folder={ownFolder} />}
        </h2>
        {ownFolder && (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => onShare(ownFolder)}
              className="cursor-pointer rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
            >
              Share
            </button>
            {!ownFolder.is_default && (
              <button
                type="button"
                onClick={() => onDelete(ownFolder)}
                className="cursor-pointer rounded-md border border-border px-2.5 py-1 text-[12.5px] text-muted-foreground hover:text-rose-500"
              >
                Delete
              </button>
            )}
          </div>
        )}
      </div>
      {error ? <p className="text-[13px] text-rose-500">{error}</p> : null}
      {/* Other folders surface as drop targets only while a session drag is in
          flight — the drill view otherwise has no folder list to drop onto. */}
      {dragActive && !folder.shared && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-[var(--color-brand-300)] bg-[var(--color-brand-50)]/40 px-3 py-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Move to
          </span>
          {folders
            .filter((f) => f.id !== folder.id)
            .map((f) => (
              <FolderDropChip
                key={f.id}
                folder={f}
                onDrop={(rowIds) => onDropSessions(rowIds, f.id)}
              />
            ))}
        </div>
      )}
      {/* Sorting moved into the column headers, where a table keeps it. What
          is left is a group-by, and one quiet control says that better than
          ten pills that outweighed the rows beneath them. */}
      <div className="mb-2 flex flex-wrap items-center justify-end gap-2">
        <GroupBySelect value={view} onChange={onChangeView} />
        {!folder.shared && <SessionUpload onUploaded={onUploaded} bare />}
      </div>
      {folderSessions === null ? (
        <p className="text-[12.5px] text-muted-foreground">Loading…</p>
      ) : (
        <>
          <SessionsView
            view={view}
            sessions={drillSessions}
            folders={folders}
            sort={sort}
            onSort={onChangeSort}
            isPinned={isPinned}
            onTogglePin={onTogglePin}
            selectedIds={folder.shared ? EMPTY_SELECTION : selectedIds}
            onToggleSelect={folder.shared ? noop : onToggleSelect}
            drag={folder.shared ? NO_DRAG : drag}
            withInstallCta={!folder.shared}
          />
          {hasMore && (
            <div ref={sentinelRef} className="flex justify-center py-4">
              <button
                type="button"
                onClick={loadMore}
                disabled={loadingMore}
                className="cursor-pointer rounded-md border border-border px-3 py-1.5 text-[12.5px] text-muted-foreground hover:text-foreground disabled:cursor-default disabled:opacity-60"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// A folder pill that lights up while a session drag hovers it.
function FolderDropChip({
  folder,
  onDrop,
}: {
  folder: SessionFolder;
  onDrop: (rowIds: string[]) => void;
}) {
  const [over, setOver] = useState(false);
  return (
    <span
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes(SESSION_DRAG_MIME)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false);
        const rowIds = readSessionDrop(e);
        if (rowIds.length === 0) return;
        e.preventDefault();
        onDrop(rowIds);
      }}
      className={
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] " +
        (over
          ? "border-[var(--color-brand-400)] bg-[var(--color-brand-50)] font-semibold text-foreground"
          : "border-border bg-base text-dim")
      }
    >
      <span aria-hidden>
        <FolderIcon />
      </span>
      {folder.name}
    </span>
  );
}

const EMPTY_SELECTION: Set<string> = new Set();
function noop() {}

// Ascending comparators; descending reverses. Ties fall back to the title so
// equal values keep a stable, readable order instead of shuffling per render.
function sortSessions(list: SessionSummary[], sort: SortKey): SessionSummary[] {
  const byColumn = {
    updated: (a: SessionSummary, b: SessionSummary) => sessionTime(a) - sessionTime(b),
    events: (a: SessionSummary, b: SessionSummary) => a.event_count - b.event_count,
    name: (a: SessionSummary, b: SessionSummary) =>
      sessionTitle(a).localeCompare(sessionTitle(b)),
    agent: (a: SessionSummary, b: SessionSummary) =>
      (a.agent_name || "").localeCompare(b.agent_name || ""),
  }[sort.column];
  const copy = [...list].sort(
    (a, b) => byColumn(a, b) || sessionTitle(a).localeCompare(sessionTitle(b)),
  );
  return sort.dir === "desc" ? copy.reverse() : copy;
}
