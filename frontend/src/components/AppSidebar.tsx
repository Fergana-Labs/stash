"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent, type MouseEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  createPage,
  type FolderContents,
  type StashItemSpec,
  type WorkspaceFile,
  type WorkspaceFolder,
  type WorkspacePage,
  type WorkspaceSidebar,
  type WorkspaceSidebarSession,
  uploadFile,
  uploadTranscript,
} from "../lib/api";
import { useShareModal } from "../lib/shareModalContext";
import { displaySessionUserName } from "../lib/sessionGrouping";
import {
  getCachedFolderContents,
  getCachedWorkspaceSidebar,
  getCachedWorkspaces,
  readCachedFolderContents,
  readCachedSidebars,
  readCachedWorkspaces,
  refreshWorkspaceSidebar,
} from "../lib/stashNavigationCache";
import type { User, Workspace } from "../lib/types";
import {
  ActivityIcon,
  DiscoverIcon,
  FileIcon,
  FolderIcon,
  HelpIcon,
  PageIcon,
  PersonIcon,
  SessionsIcon,
  SettingsIcon,
  StashIcon,
  TableIcon,
} from "./StashIcons";

interface AppSidebarProps {
  user?: User;
  onLogout?: () => void;
  cmdkOpen?: boolean;
  onCmdkOpen?: () => void;
  activeWorkspaceId?: string | null;
}

interface WorkspaceNode extends Workspace {
  shared?: boolean;
}

type SidebarSection = "sessions" | "files" | "stashes";
type DropSection = "sessions" | "files";
type DropStatus = "idle" | "over" | "saving" | "done" | "error";
type PinMenuState = {
  kind: PinKind;
  id: string;
  label: string;
  pinned: boolean;
  x: number;
  y: number;
};

interface SidebarDropState {
  key: string | null;
  status: DropStatus;
  message: string;
}

const OPEN_WORKSPACES_KEY = "stash_sidebar_open_workspaces";
const OPEN_SECTIONS_KEY = "stash_sidebar_open_sections";
const COLLAPSED_STASHES_KEY = "stash_sidebar_collapsed_stashes";
const PINNED_FS_KEY = "stash_sidebar_pinned_files_folders";
const PINNED_FS_LABELS_KEY = "stash_sidebar_pinned_files_folders_labels";
const LAST_WORKSPACE_KEY = "stash_sidebar_last_workspace";
const PREVIEW_ITEM_LIMIT = 10;
const EMPTY_PIN_STATE = { folders: [], files: [] };

type PinKind = "folder" | "file";
type PinnedLabels = {
  folders: Record<string, string>;
  files: Record<string, string>;
};

function readBooleanMap(key: string): Record<string, boolean> {
  if (typeof window === "undefined") return {};

  const raw = window.localStorage.getItem(key);
  if (!raw) return {};

  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    window.localStorage.removeItem(key);
    return {};
  }
}

function writeBooleanMap(key: string, value: Record<string, boolean>) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

function readPinnedMap(): Record<string, { folders: string[]; files: string[] }> {
  if (typeof window === "undefined") return {};

  const raw = window.localStorage.getItem(PINNED_FS_KEY);
  if (!raw) return {};

  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    window.localStorage.removeItem(PINNED_FS_KEY);
    return {};
  }
}

function writePinnedMap(value: Record<string, { folders: string[]; files: string[] }>) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PINNED_FS_KEY, JSON.stringify(value));
}

function readPinnedLabelMap(): Record<string, PinnedLabels> {
  if (typeof window === "undefined") return {};

  const raw = window.localStorage.getItem(PINNED_FS_LABELS_KEY);
  if (!raw) return {};

  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    window.localStorage.removeItem(PINNED_FS_KEY);
    window.localStorage.removeItem(PINNED_FS_LABELS_KEY);
    return {};
  }
}

function writePinnedLabelMap(value: Record<string, PinnedLabels>) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PINNED_FS_LABELS_KEY, JSON.stringify(value));
}

function sectionKey(workspaceId: string, section: SidebarSection): string {
  return `${workspaceId}:${section}`;
}

function stashCollapseKey(workspaceId: string, stashId: string): string {
  return `${workspaceId}:${stashId}`;
}

function dropKey(workspaceId: string, section: DropSection): string {
  return `${workspaceId}:${section}`;
}

function isFilesDrag(event: DragEvent<HTMLElement>): boolean {
  return Array.from(event.dataTransfer.types).includes("Files");
}

function isJsonl(file: File): boolean {
  return file.name.toLowerCase().endsWith(".jsonl");
}

function sessionIdFromFile(file: File): string {
  return file.name.replace(/\.jsonl$/i, "").trim();
}

function ChevronToggle({
  open,
  ariaLabel,
  onToggle,
  hoverOnly,
}: {
  open?: boolean;
  ariaLabel?: string;
  onToggle: () => void;
  // hoverOnly: chevron is invisible until the nearest `group/section`
  // ancestor is hovered or until the section is closed. Closed-state stays
  // visible so users have an affordance to reopen a collapsed section.
  hoverOnly?: boolean;
}) {
  const visibility = hoverOnly
    ? (open
        ? "opacity-0 group-hover/section:opacity-100 transition-opacity"
        : "opacity-60 group-hover/section:opacity-100 transition-opacity")
    : "";
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
      className={
        "-ml-0.5 flex h-4 w-4 items-center justify-center rounded text-muted hover:bg-base/60 hover:text-foreground " +
        visibility
      }
      aria-expanded={open}
      aria-label={ariaLabel ?? "Toggle"}
    >
      <svg
        className={"chev h-3 w-3" + (open ? " rotate-90" : "")}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </button>
  );
}

function NavRow({
  href,
  icon,
  label,
  active,
  onClick,
  onContextMenu,
  trailing,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  onContextMenu?: (event: MouseEvent<HTMLAnchorElement>) => void;
  trailing?: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={
        "page-row flex items-center gap-2 rounded-md px-2 py-1 text-[13px] transition-colors " +
        (active
          ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)]"
          : "text-dim hover:bg-raised hover:text-foreground")
      }
      onClick={onClick}
      onContextMenu={onContextMenu}
    >
      <span className="flex h-4 w-4 items-center justify-center text-[14px]">{icon}</span>
      <span className="flex-1 truncate">{label}</span>
      {trailing}
    </Link>
  );
}

function DisabledNavRow({
  icon,
  label,
}: {
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <div className="page-row flex cursor-not-allowed items-center gap-2 rounded-md px-2 py-1 text-[13px] text-muted/50">
      <span className="flex h-4 w-4 items-center justify-center">{icon}</span>
      <span className="truncate">{label}</span>
    </div>
  );
}

function PinMenu({
  state,
  onClose,
  onTogglePin,
  menuRef,
}: {
      state: PinMenuState;
      onClose: () => void;
      onTogglePin: () => void;
      menuRef: { current: HTMLDivElement | null };
}) {
  return (
    <div
      ref={menuRef}
      className="fixed z-40 rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg"
      style={{ left: state.x, top: state.y }}
      role="menu"
    >
      <button
        type="button"
        role="menuitem"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onTogglePin();
          onClose();
        }}
        className="w-full px-3 py-1.5 text-left text-foreground hover:bg-raised"
      >
        {state.pinned ? `Unpin ${state.label}` : `Pin ${state.label}`}
      </button>
    </div>
  );
}

function CreatePageModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;

    setSubmitting(true);
    setError("");
    try {
      await onCreate(trimmed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create page");
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-start justify-center bg-black/30 px-4 pt-[18vh]"
      onClick={onClose}
    >
      <form
        onSubmit={submit}
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-sm overflow-hidden rounded-lg border border-border bg-base shadow-2xl"
      >
        <div className="border-b border-border px-4 py-3">
          <h2 className="font-display text-[17px] font-semibold text-foreground">
            New page
          </h2>
          <p className="mt-1 text-[12px] text-muted">
            Name the page before adding it to Files.
          </p>
        </div>
        <div className="p-4">
          <input
            ref={inputRef}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Untitled"
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[14px] text-foreground outline-none placeholder:text-muted focus:border-[var(--color-brand-400)]"
          />
          {error ? (
            <div className="mt-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[12px] text-red-700">
              {error}
            </div>
          ) : null}
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border px-3 py-1.5 text-[13px] text-muted hover:bg-raised hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
            >
              {submitting ? "Creating..." : "Create"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

function SectionAddRow({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onClick();
      }}
      className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-[12.5px] text-muted hover:bg-raised hover:text-foreground"
    >
      <span className="flex h-4 w-4 items-center justify-center text-[14px]">+</span>
      <span className="flex-1 truncate">{label}</span>
    </button>
  );
}

function WorkspaceTree({
  workspace,
  spine,
  pathname,
  openSections,
  onSectionOpenChange,
  dropState,
  onDropFiles,
  onDropHover,
  pinnedFolders,
  pinnedFiles,
  pinnedLabels,
  collapsedStashes,
  onPinToggle,
  onUnpinAll,
  onStashCollapsedChange,
  onAddSession,
  onAddPage,
  onAddStash,
}: {
  workspace: WorkspaceNode;
  spine: WorkspaceSidebar | null;
  pathname: string;
  openSections: Record<SidebarSection, boolean>;
  onSectionOpenChange: (section: SidebarSection, open: boolean) => void;
  dropState: SidebarDropState;
  onDropFiles: (workspaceId: string, section: DropSection, files: FileList) => void;
  onDropHover: (workspaceId: string, section: DropSection, active: boolean) => void;
  pinnedFolders: string[];
  pinnedFiles: string[];
  pinnedLabels: PinnedLabels;
  collapsedStashes: Record<string, boolean>;
  onPinToggle: (kind: PinKind, workspaceId: string, id: string, label?: string) => void;
  onUnpinAll: (workspaceId: string) => void;
  onStashCollapsedChange: (workspaceId: string, stashId: string, collapsed: boolean) => void;
  onAddSession: (workspaceId: string) => void;
  onAddPage: (workspaceId: string) => void;
  onAddStash: (workspaceId: string) => void;
}) {
  const dropProps = (section: DropSection) => ({
    onDragOver(event: DragEvent<HTMLElement>) {
      if (!isFilesDrag(event)) return;
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = "copy";
      onDropHover(workspace.id, section, true);
    },
    onDragLeave(event: DragEvent<HTMLElement>) {
      if (!isFilesDrag(event)) return;
      event.preventDefault();
      event.stopPropagation();
      onDropHover(workspace.id, section, false);
    },
    onDrop(event: DragEvent<HTMLElement>) {
      if (!isFilesDrag(event)) return;
      event.preventDefault();
      event.stopPropagation();
      onDropFiles(workspace.id, section, event.dataTransfer.files);
    },
  });
  const sessionsDrop = dropState.key === dropKey(workspace.id, "sessions") ? dropState : null;

  // pathname kept in props for parity with active-row styling deeper in the tree.
  void pathname;

  return (
      <div className="space-y-0.5">
      <StashesBlock
        workspace={workspace}
        spine={spine}
        open={openSections.stashes}
        onOpenChange={(nextOpen) => onSectionOpenChange("stashes", nextOpen)}
        collapsedStashes={collapsedStashes}
        onStashCollapsedChange={(stashId, collapsed) =>
          onStashCollapsedChange(workspace.id, stashId, collapsed)
        }
        onAddStash={() => onAddStash(workspace.id)}
      />

      <details
        open={openSections.sessions}
        onToggle={(e) => onSectionOpenChange("sessions", e.currentTarget.open)}
        className="group/section text-[13px]"
        {...dropProps("sessions")}
        >
          <summary
            onClick={(e) => {
              e.preventDefault();
              onSectionOpenChange("sessions", true);
            }}
            className={
              "page-row flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-raised " +
              (sessionsDrop?.status === "over"
                ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)] ring-1 ring-[var(--color-brand-300)]"
                : "")
            }
          >
            <Link
              href={`/workspaces/${workspace.id}/sessions`}
              onClick={(event) => {
                event.stopPropagation();
                onSectionOpenChange("sessions", true);
              }}
              className="flex-1 truncate text-[11px] font-semibold uppercase tracking-wide text-muted hover:text-foreground"
            >
              Sessions
            </Link>
            <ChevronToggle
              open={openSections.sessions}
              onToggle={() => onSectionOpenChange("sessions", !openSections.sessions)}
              hoverOnly
            />
          </summary>
        <div className="ml-3 space-y-0.5 border-l border-border pl-2">
            {sessionsDrop?.message ? <DropMessage state={sessionsDrop} /> : null}
            {groupSidebarSessions(spine?.sessions ?? []).map((group, index) => (
              <SessionTreeDetails
                key={group.dateKey}
                workspaceId={workspace.id}
                group={group}
                initialOpen={index === 0}
              />
            ))}
            {(!spine || spine.sessions.length === 0) && (
              <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
            )}
            <SectionAddRow label="New session" onClick={() => onAddSession(workspace.id)} />
          </div>
        </details>

        <FilesBlock
          workspace={workspace}
          spine={spine}
          open={openSections.files}
          onOpenChange={(nextOpen) => onSectionOpenChange("files", nextOpen)}
          dropState={dropState}
          dropProps={dropProps("files")}
          pinnedFolders={pinnedFolders}
          pinnedFiles={pinnedFiles}
          pinnedLabels={pinnedLabels}
          onPinToggle={(kind, id, label) => onPinToggle(kind, workspace.id, id, label)}
          onUnpinAll={() => onUnpinAll(workspace.id)}
          onAddPage={() => onAddPage(workspace.id)}
        />
    </div>
  );
}

function fileIconClass(contentType: string | undefined): string {
  if (contentType?.includes("pdf")) return "text-rose-500";
  if (contentType?.includes("csv")) return "text-emerald-600";
  if (contentType?.includes("html")) return "text-amber-600";
  return "text-muted";
}

function sessionLabelForSidebar(session: WorkspaceSidebarSession): string {
  const raw = (session.title || session.session_id).trim();
  return raw.length > 26 ? `${raw.slice(0, 26)}…` : raw;
}

function displaySidebarSessionUser(raw: string | null | undefined): string {
  return displaySessionUserName(raw, "Unknown user");
}

type SessionTreeDayGroup = {
  dateKey: string;
  label: string;
  total: number;
  users: Array<{ user: string; sessions: WorkspaceSidebarSession[] }>;
};

const UNKNOWN_SESSION_DATE = "Unknown date";
const MAX_DAY_BUCKETS = 14;
const MAX_WEEK_BUCKETS = 12;

type SessionBucket = "day" | "week" | "month";

function sessionDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

// Group key per bucket: ISO date for day, ISO-week start for week, YYYY-MM
// for month. Stable enough to sort lexicographically (descending = newest).
function bucketKey(date: Date, bucket: SessionBucket): string {
  if (bucket === "day") return date.toISOString().slice(0, 10);
  if (bucket === "month") return date.toISOString().slice(0, 7);
  // Week: anchor to Monday so day-of-week jitter doesn't split a week across buckets.
  const monday = new Date(date);
  const day = (monday.getDay() + 6) % 7; // 0 = Monday
  monday.setDate(monday.getDate() - day);
  return monday.toISOString().slice(0, 10) + "/W";
}

function formatBucketLabel(key: string, bucket: SessionBucket): string {
  if (key === UNKNOWN_SESSION_DATE) return key;
  if (bucket === "day") {
    return new Date(`${key}T12:00:00`).toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  }
  if (bucket === "month") {
    return new Date(`${key}-15T12:00:00`).toLocaleDateString(undefined, {
      month: "long",
      year: "numeric",
    });
  }
  const monday = new Date(`${key.replace("/W", "")}T12:00:00`);
  const sunday = new Date(monday);
  sunday.setDate(sunday.getDate() + 6);
  const sameMonth = monday.getMonth() === sunday.getMonth();
  const left = monday.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const right = sunday.toLocaleDateString(undefined, sameMonth ? { day: "numeric" } : { month: "short", day: "numeric" });
  return `Week of ${left}–${right}`;
}

// Pick the coarsest bucket that keeps the sidebar list short. If grouping by
// day would produce more than MAX_DAY_BUCKETS distinct days, roll up to weeks;
// if weeks still overflow, roll up to months. The user can always click into
// the Sessions page to see everything ungrouped.
function chooseSessionBucket(sessions: WorkspaceSidebarSession[]): SessionBucket {
  const days = new Set<string>();
  for (const session of sessions) {
    const date = sessionDate(session.last_at || session.updated_at);
    if (date) days.add(date.toISOString().slice(0, 10));
  }
  if (days.size <= MAX_DAY_BUCKETS) return "day";

  const weeks = new Set<string>();
  for (const session of sessions) {
    const date = sessionDate(session.last_at || session.updated_at);
    if (date) weeks.add(bucketKey(date, "week"));
  }
  if (weeks.size <= MAX_WEEK_BUCKETS) return "week";

  return "month";
}

function groupSidebarSessions(sessions: WorkspaceSidebarSession[]): SessionTreeDayGroup[] {
  const bucket = chooseSessionBucket(sessions);
  const byBucket = new Map<string, Map<string, WorkspaceSidebarSession[]>>();
  for (const session of sessions) {
    const date = sessionDate(session.last_at || session.updated_at);
    const key = date ? bucketKey(date, bucket) : UNKNOWN_SESSION_DATE;
    const user = displaySidebarSessionUser(session.agent_name);
    const users = byBucket.get(key) ?? new Map<string, WorkspaceSidebarSession[]>();
    users.set(user, [...(users.get(user) ?? []), session]);
    byBucket.set(key, users);
  }

  return Array.from(byBucket.entries())
    .sort(([a], [b]) => {
      if (a === UNKNOWN_SESSION_DATE) return 1;
      if (b === UNKNOWN_SESSION_DATE) return -1;
      return b.localeCompare(a);
    })
    .map(([key, usersByName]) => {
      const users = Array.from(usersByName.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([user, sessionRows]) => ({
          user,
          sessions: sessionRows,
        }));
      const total = users.reduce((sum, b) => sum + b.sessions.length, 0);
      return {
        dateKey: key,
        label: formatBucketLabel(key, bucket),
        total,
        users,
      };
    });
}

function SessionTreeDetails({
  workspaceId,
  group,
  initialOpen,
}: {
  workspaceId: string;
  group: SessionTreeDayGroup;
  initialOpen?: boolean;
}) {
  const [open, setOpen] = useState(!!initialOpen);
  return (
    <details open={open} className="text-[12.5px]">
      <summary
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen(true);
        }}
        className="page-row flex items-center gap-1 rounded-md px-2 py-1 hover:bg-raised"
      >
        <ChevronToggle open={open} onToggle={() => setOpen((current) => !current)} />
        <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
          <FolderIcon />
        </span>
        <span className="flex-1 truncate text-foreground">{group.label}</span>
        <span className="text-[10.5px] text-muted">{group.total}</span>
      </summary>
      <div className="ml-2.5 space-y-0.5 border-l border-border pl-2">
        {group.users.length === 0 ? (
          <div className="px-2 py-1 text-[11px] italic text-muted">no sessions</div>
        ) : (
          group.users.map((bucket) => (
            <SessionUserFolder
              key={`${group.dateKey}-${bucket.user}`}
              workspaceId={workspaceId}
              bucket={bucket}
            />
          ))
        )}
      </div>
    </details>
  );
}

function SessionUserFolder({
  workspaceId,
  bucket,
}: {
  workspaceId: string;
  bucket: { user: string; sessions: WorkspaceSidebarSession[] };
}) {
  // Default collapsed — opening a date bucket already reveals N user rows,
  // and auto-expanding each one explodes the whole tree on first paint.
  const [open, setOpen] = useState(false);
  return (
    <details open={open} className="text-[12px]">
      <summary
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen(true);
        }}
        className="page-row flex items-center gap-1 rounded-md px-2 py-0.5 hover:bg-raised"
      >
        <ChevronToggle open={open} onToggle={() => setOpen((current) => !current)} />
        <span className="flex h-4 w-4 items-center justify-center text-[13px] text-muted">
          <PersonIcon />
        </span>
        <span className="flex-1 truncate text-muted">{bucket.user}</span>
        <span className="text-[10px] text-muted">{bucket.sessions.length}</span>
      </summary>
      <div className="ml-2.5 space-y-0.5 border-l border-border pl-2">
        {bucket.sessions.map((s) => (
          <NavRow
            key={s.session_id}
            href={`/workspaces/${workspaceId}/sessions/${encodeURIComponent(s.session_id)}`}
            icon={<span className="text-muted"><SessionsIcon /></span>}
            label={sessionLabelForSidebar(s)}
          />
        ))}
      </div>
    </details>
  );
}

type StashTreeKind = "session" | "folder" | "page" | "file" | "table" | "other";

type StashTreeItem = {
  kind: StashTreeKind;
  key: string;
  href?: string;
  label: string;
  icon: React.ReactNode;
};

function resolveFolderPath(
  folderId: string | null,
  foldersById: Map<string, WorkspaceFolder>,
  cache: Map<string, string>,
  stack = new Set<string>()
): string {
  if (!folderId) return "";
  const cached = cache.get(folderId);
  if (cached !== undefined) return cached;
  if (stack.has(folderId)) return "";
  const folder = foldersById.get(folderId);
  if (!folder) return "";

  stack.add(folderId);
  const parentPath = resolveFolderPath(folder.parent_folder_id, foldersById, cache, stack);
  const next = parentPath ? `${parentPath}/${folder.name}` : folder.name;
  cache.set(folderId, next);
  return next;
}

function buildStashTreeItems(
  workspaceId: string,
  items: StashItemSpec[],
  folderById: Map<string, WorkspaceFolder>,
  pageById: Map<string, WorkspacePage>,
  fileById: Map<string, WorkspaceFile>,
  sessionById: Map<string, WorkspaceSidebarSession>,
  sessionBySessionId: Map<string, WorkspaceSidebarSession>
): StashTreeItem[] {
  const pathCache = new Map<string, string>();
  return [...items]
    .sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
    .map((item, index) => {
      if (item.object_type === "session") {
        const session = sessionById.get(item.object_id) ?? sessionBySessionId.get(item.object_id);
        const fallback = `Session ${item.object_id}`;
        return {
          kind: "session",
          key: `${item.object_id}:${index}`,
          href: session ? `/workspaces/${workspaceId}/sessions/${encodeURIComponent(session.session_id)}` : undefined,
          icon: <span className="text-muted"><SessionsIcon /></span>,
          label: item.label_override ?? (session ? session.title || session.session_id : fallback),
        };
      }

      if (item.object_type === "folder") {
        const folder = folderById.get(item.object_id);
        return {
          kind: "folder",
          key: `${item.object_id}:${index}`,
          href: folder ? `/workspaces/${workspaceId}/folders/${item.object_id}` : undefined,
          icon: <span className="text-muted"><FolderIcon /></span>,
          label:
            item.label_override ??
            (folder ? resolveFolderPath(folder.id, folderById, pathCache) : `Folder ${item.object_id}`),
        };
      }

      if (item.object_type === "page") {
        const page = pageById.get(item.object_id);
        if (!page) {
          return {
            kind: "page",
            key: `${item.object_id}:${index}`,
            icon: <span className="text-muted"><PageIcon /></span>,
            label: item.label_override ?? `Page ${item.object_id}`,
          };
        }

        const folderPath = resolveFolderPath(page.folder_id, folderById, pathCache);
        const pagePath = folderPath ? `${folderPath}/${page.name}` : page.name;
        return {
          kind: "page",
          key: `${item.object_id}:${index}`,
          href: `/workspaces/${workspaceId}/p/${page.id}`,
          icon: <span className="text-muted"><PageIcon /></span>,
          label: item.label_override ?? pagePath,
        };
      }

      if (item.object_type === "file") {
        const file = fileById.get(item.object_id);
        if (!file) {
          return {
            kind: "file",
            key: `${item.object_id}:${index}`,
            icon: <span className={fileIconClass(undefined)}><FileIcon /></span>,
            label: item.label_override ?? `File ${item.object_id}`,
          };
        }

        const folderPath = resolveFolderPath(file.folder_id, folderById, pathCache);
        const filePath = folderPath ? `${folderPath}/${file.name}` : file.name;
        return {
          kind: "file",
          key: `${item.object_id}:${index}`,
          href: `/workspaces/${workspaceId}/f/${file.id}`,
          icon: <span className={fileIconClass(file.content_type)}><FileIcon /></span>,
          label: item.label_override ?? filePath,
        };
      }

      if (item.object_type === "table") {
        return {
          kind: "table",
          key: `${item.object_id}:${index}`,
          href: `/tables/${item.object_id}?workspaceId=${workspaceId}`,
          icon: <span className="text-muted"><TableIcon /></span>,
          label: item.label_override ?? `Table ${item.object_id}`,
        };
      }

      return {
        kind: "other",
        key: `${item.object_id}:${index}`,
        icon: <span className="text-muted"><FolderIcon /></span>,
        label: item.label_override ?? `${item.object_type} ${item.object_id}`,
      };
    });
}

function StashTreeRow({ row }: { row: StashTreeItem }) {
  if (!row.href) {
    return (
      <div className="page-row flex items-center gap-2 rounded-md px-2 py-0.5 text-[12.5px] text-muted">
        <span className="flex h-4 w-4 items-center justify-center text-[14px]">{row.icon}</span>
        <span className="flex-1 truncate">{row.label}</span>
      </div>
    );
  }

  return (
    <NavRow href={row.href} icon={row.icon} label={row.label} />
  );
}

function FileNavRow({
  workspaceId,
  file,
  label,
  onClick,
  onPinMenu,
}: {
  workspaceId: string;
  file: Pick<WorkspaceFile, "id" | "name" | "content_type" | "linked_table_id">;
  label: string;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  onPinMenu?: (event: MouseEvent<HTMLAnchorElement>) => void;
}) {
  const isCsvLinked =
    file.content_type?.includes("csv") && file.linked_table_id;
  const href = isCsvLinked
    ? `/tables/${file.linked_table_id}?workspaceId=${workspaceId}`
    : `/workspaces/${workspaceId}/f/${file.id}`;
  return (
    <NavRow
      href={href}
      icon={
        <span className={fileIconClass(file.content_type)}>
          {file.content_type?.includes("csv") ? <TableIcon /> : <FileIcon />}
        </span>
      }
      label={label}
      onClick={onClick}
      trailing={null}
      onContextMenu={onPinMenu}
    />
  );
}

function DropMessage({ state }: { state: SidebarDropState }) {
  const tone =
    state.status === "error"
      ? "text-red-600"
      : state.status === "done"
        ? "text-[var(--color-brand-700)]"
        : "text-muted";

  return (
    <div className={"px-2 py-1 text-[11px] " + tone}>
      {state.message}
    </div>
  );
}

function FolderTreeNode({
  workspaceId,
  folderId,
  name,
  isFolderPinned,
  isFilePinned,
  onPinMenu,
}: {
  workspaceId: string;
  folderId: string;
  name: string;
  isFolderPinned: (folderId: string) => boolean;
  isFilePinned: (fileId: string) => boolean;
  onPinMenu?: (event: MouseEvent<HTMLElement>, kind: PinKind, id: string, label: string, pinned: boolean) => void;
}) {
  const cachedContents = readCachedFolderContents(folderId);
  const [contents, setContents] = useState<FolderContents | null>(cachedContents);
  const [loaded, setLoaded] = useState(!!cachedContents);
  const [open, setOpen] = useState(false);

  const loadContents = useCallback(() => {
    if (loaded) return;
    setLoaded(true);
    getCachedFolderContents(workspaceId, folderId)
      .then(setContents)
      .catch(() =>
        setContents({
          folder: { id: folderId, name, parent_folder_id: null },
          breadcrumbs: [],
          subfolders: [],
          pages: [],
          files: [],
        })
      );
  }, [loaded, workspaceId, folderId, name]);

  const openFolder = useCallback(() => {
    setOpen(true);
    loadContents();
  }, [loadContents]);

  const handleToggle = useCallback(() => {
    const next = !open;
    setOpen(next);
    if (next) loadContents();
  }, [open, loadContents]);

  return (
    <details open={open} className="text-[12.5px]">
      <summary
        onContextMenu={(event) => {
          event.preventDefault();
          onPinMenu?.(
            event,
            "folder",
            folderId,
            name,
            isFolderPinned(folderId)
          );
        }}
        onClick={(e) => {
          e.preventDefault();
          openFolder();
        }}
        className="page-row flex items-center gap-1 rounded-md px-2 py-0.5 hover:bg-raised"
      >
        <ChevronToggle open={open} onToggle={handleToggle} />
        <span className="flex h-4 w-4 items-center justify-center text-muted">
          <FolderIcon />
        </span>
        <Link
          href={`/workspaces/${workspaceId}/folders/${folderId}`}
          onClick={(event) => {
            event.stopPropagation();
            openFolder();
          }}
          className="flex-1 truncate text-left text-foreground hover:text-[var(--color-brand-700)]"
        >
          {name}
        </Link>
      </summary>
      <div className="ml-2.5 space-y-0.5 border-l border-border pl-2">
        {contents === null && loaded && (
          <div className="px-2 py-1 text-[11px] italic text-muted">loading…</div>
        )}
        {contents?.subfolders
          .filter((sub) => !isFolderPinned(sub.id))
          .map((sub) => (
            <FolderTreeNode
              key={sub.id}
              workspaceId={workspaceId}
              folderId={sub.id}
              name={sub.name}
              isFolderPinned={isFolderPinned}
              isFilePinned={isFilePinned}
              onPinMenu={onPinMenu}
            />
          ))}
        {contents?.pages.map((p) => (
          <NavRow
            key={p.id}
            href={`/workspaces/${workspaceId}/p/${p.id}`}
            icon={<PageIcon className="text-muted" />}
            label={p.name}
          />
        ))}
        {contents?.files
          .filter((f) => !isFilePinned(f.id))
          .map((f) => (
            <FileNavRow
              key={f.id}
              workspaceId={workspaceId}
              file={f}
              label={f.name}
              onPinMenu={(event) =>
                onPinMenu?.(event, "file", f.id, f.name, isFilePinned(f.id))
              }
            />
        ))}
        {contents &&
          contents.subfolders.length === 0 &&
          contents.pages.length === 0 &&
          contents.files.length === 0 && (
            <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
          )}
      </div>
    </details>
  );
}

function FilesBlock({
  workspace,
  spine,
  open,
  onOpenChange,
  dropState,
  dropProps,
  pinnedFolders,
  pinnedFiles,
  pinnedLabels,
  onPinToggle,
  onUnpinAll,
  onAddPage,
}: {
  workspace: WorkspaceNode;
  spine: WorkspaceSidebar | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dropState: SidebarDropState;
  dropProps: {
    onDragOver: (event: DragEvent<HTMLElement>) => void;
    onDragLeave: (event: DragEvent<HTMLElement>) => void;
    onDrop: (event: DragEvent<HTMLElement>) => void;
  };
  pinnedFolders: string[];
  pinnedFiles: string[];
  pinnedLabels: PinnedLabels;
  onPinToggle: (kind: PinKind, id: string, label?: string) => void;
  onUnpinAll: () => void;
  onAddPage: () => void;
}) {
  const tree = spine?.files;
  const folders = tree?.folders ?? [];
  const pages = tree?.pages ?? [];
  const files = tree?.files ?? [];
  const pinnedFolderSet = new Set(pinnedFolders);
  const pinnedFileSet = new Set(pinnedFiles);
  const visibleFolders = folders.filter((folder) => !pinnedFolderSet.has(folder.id));
  const visibleFiles = files.filter((file) => !pinnedFileSet.has(file.id));
  const rootFolders = visibleFolders.filter((f) => !f.parent_folder_id);
  const rootPages = pages.filter((p) => !p.folder_id);
  const rootFiles = visibleFiles.filter((f) => !f.folder_id);
  const folderById = new Map((tree?.folders ?? []).map((folder) => [folder.id, folder]));
  const fileById = new Map((tree?.files ?? []).map((file) => [file.id, file]));
  const pinnedFolderRows = pinnedFolders.map((id) => {
    const folder = folderById.get(id);
    const label = pinnedLabels.folders[id] ?? folder?.name ?? "Folder";
    return {
      id,
      label,
      href: `/workspaces/${workspace.id}/folders/${id}`,
      icon: <FolderIcon />,
    };
  });
  const pinnedFileRows = pinnedFiles.map((id) => {
    const file = fileById.get(id);
    if (!file) {
      return {
        id,
        label: "File",
        href: `/workspaces/${workspace.id}/f/${id}`,
        icon: <span className={fileIconClass(undefined)}><FileIcon /></span>,
      };
    }
    const label = pinnedLabels.files[id] ?? file.name;
    const isCsvLinked = file.content_type?.includes("csv") && file.linked_table_id;
    return {
      id,
      label,
      href: isCsvLinked
        ? `/tables/${file.linked_table_id}?workspaceId=${workspace.id}`
        : `/workspaces/${workspace.id}/f/${id}`,
      icon:
        <span className={fileIconClass(file.content_type)}>
          {file.content_type?.includes("csv") ? <TableIcon /> : <FileIcon />}
        </span>,
    };
  });
  const total = folders.length + pages.length + files.length;
  const filesDrop = dropState.key === dropKey(workspace.id, "files") ? dropState : null;
  const [pinMenu, setPinMenu] = useState<PinMenuState | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuClamp =
    pinMenu && typeof window !== "undefined"
      ? {
          x: Math.max(0, Math.min(pinMenu.x, window.innerWidth - 190)),
          y: Math.max(0, Math.min(pinMenu.y, window.innerHeight - 72)),
        }
      : pinMenu;

  useEffect(() => {
    if (!pinMenu) return;

    const onDown = (event: globalThis.MouseEvent) => {
      if (menuRef.current && menuRef.current.contains(event.target as Node)) return;
      setPinMenu(null);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setPinMenu(null);
    };

    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);

    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [pinMenu]);

  const pinnedCount = pinnedFolders.length + pinnedFiles.length;
  const renderPinned = pinnedCount > 0;

  function showPinMenu(
    event: MouseEvent<HTMLElement>,
    kind: PinKind,
    id: string,
    label: string,
    pinned: boolean
  ) {
    event.preventDefault();
    event.stopPropagation();
    setPinMenu({ kind, id, label, pinned, x: event.clientX, y: event.clientY });
  }

  return (
    <details
      open={open}
      onToggle={(e) => onOpenChange(e.currentTarget.open)}
      className="group/section text-[13px]"
      {...dropProps}
    >
      <summary
        onClick={(e) => {
          e.preventDefault();
          onOpenChange(true);
        }}
        className={
          "page-row flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-raised " +
          (filesDrop?.status === "over"
            ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)] ring-1 ring-[var(--color-brand-300)]"
            : "")
        }
      >
        <span className="flex-1 truncate text-[11px] font-semibold uppercase tracking-wide text-muted">
          Files
        </span>
        <ChevronToggle open={open} onToggle={() => onOpenChange(!open)} hoverOnly />
      </summary>
      <div className="ml-3 space-y-0.5 border-l border-border pl-2">
        {filesDrop?.message ? <DropMessage state={filesDrop} /> : null}
            {renderPinned ? (
              <div className="space-y-0.5">
                <div className="flex items-center justify-between gap-2 px-2 py-0.5">
                  <span className="text-[10px] uppercase tracking-wide text-muted">
                    Pinned ({pinnedCount})
                  </span>
              <button
                type="button"
                onClick={(event) => {
                  event.preventDefault();
                  onUnpinAll();
                }}
                className="rounded px-1 py-0.5 text-[10px] text-[var(--color-brand-700)] hover:bg-[var(--color-brand-50)]"
                aria-label="Unpin all files and folders"
              >
                    Unpin all
                  </button>
                </div>
                {pinnedFolderRows.map((folder) => (
                  <NavRow
                    key={`pinned-folder-${folder.id}`}
                    href={folder.href}
                    icon={folder.icon}
                    label={folder.label}
                    onContextMenu={(event) =>
                      showPinMenu(event, "folder", folder.id, folder.label, true)
                    }
                  />
                ))}
                {pinnedFileRows.map((file) => (
                  <NavRow
                    key={`pinned-file-${file.id}`}
                    href={file.href}
                    icon={file.icon}
                    label={file.label}
                    onContextMenu={(event) =>
                      showPinMenu(event, "file", file.id, file.label, true)
                    }
                  />
                ))}
              </div>
            ) : null}
        {rootFolders.map((f) => (
          <FolderTreeNode
            key={f.id}
            workspaceId={workspace.id}
            folderId={f.id}
            name={f.name}
            isFolderPinned={(folderId) => pinnedFolderSet.has(folderId)}
            isFilePinned={(fileId) => pinnedFileSet.has(fileId)}
            onPinMenu={showPinMenu}
          />
        ))}
        {rootPages.slice(0, PREVIEW_ITEM_LIMIT).map((p) => (
          <NavRow
            key={p.id}
            href={`/workspaces/${workspace.id}/p/${p.id}`}
            icon={<PageIcon className="text-muted" />}
            label={p.name}
            onClick={() => onOpenChange(true)}
          />
        ))}
        {rootFiles.slice(0, PREVIEW_ITEM_LIMIT).map((f) => (
          <FileNavRow
            key={f.id}
            workspaceId={workspace.id}
            file={f}
            label={f.name}
            onClick={() => onOpenChange(true)}
            onPinMenu={(event) =>
              showPinMenu(event, "file", f.id, f.name, pinnedFileSet.has(f.id))
            }
          />
        ))}
        {!spine || total === 0 ? (
          <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
        ) : null}
        <SectionAddRow label="New page" onClick={onAddPage} />
        {pinMenu && menuClamp ? (
          <PinMenu
            state={{
              ...pinMenu,
              x: menuClamp.x,
              y: menuClamp.y,
            }}
            onClose={() => setPinMenu(null)}
            onTogglePin={() => onPinToggle(pinMenu.kind, pinMenu.id, pinMenu.label)}
            menuRef={menuRef}
          />
        ) : null}
      </div>
    </details>
  );
}

function StashesBlock({
  workspace,
  spine,
  open,
  onOpenChange,
  collapsedStashes,
  onStashCollapsedChange,
  onAddStash,
}: {
  workspace: WorkspaceNode;
  spine: WorkspaceSidebar | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collapsedStashes: Record<string, boolean>;
  onStashCollapsedChange: (stashId: string, collapsed: boolean) => void;
  onAddStash: () => void;
}) {
  const stashes = spine?.stashes ?? [];
  const tree = spine?.files;
  const foldersById = new Map(
    (tree?.folders ?? []).map((folder) => [folder.id, folder])
  );
  const pagesById = new Map(
    (tree?.pages ?? []).map((page) => [page.id, page])
  );
  const filesById = new Map(
    (tree?.files ?? []).map((file) => [file.id, file])
  );

  const sessionById = new Map<string, WorkspaceSidebarSession>();
  const sessionBySessionId = new Map<string, WorkspaceSidebarSession>();
  for (const session of spine?.sessions ?? []) {
    if (session.id) sessionById.set(session.id, session);
    sessionBySessionId.set(session.session_id, session);
  }

  const nativeStashes = stashes.filter((stash) => !stash.forked_from_stash_id);
  const forkedStashes = stashes.filter((stash) => stash.forked_from_stash_id);

  function renderStashGroup(
    title: string | null,
    items: typeof stashes,
    includeEmpty = false
  ) {
    if (items.length === 0 && !includeEmpty) return null;

    return (
      <div className="space-y-0.5 border-l border-border pl-2">
        {title ? (
          <div className="px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted">
            {title}
          </div>
        ) : null}
        {items.length === 0 ? (
          <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
        ) : (
          items.map((stash) => {
            const collapsed =
              collapsedStashes[stashCollapseKey(workspace.id, stash.id)] === true;
            const children = buildStashTreeItems(
              workspace.id,
              stash.items ?? [],
              foldersById,
              pagesById,
              filesById,
              sessionById,
              sessionBySessionId
            );

            return (
              <div key={`${title}-${stash.id}`} className="space-y-0.5">
                <div className="page-row flex items-center gap-1 rounded-md px-2 py-0.5 hover:bg-raised">
                  <ChevronToggle
                    open={!collapsed}
                    ariaLabel={`${collapsed ? "Expand" : "Collapse"} ${stash.title}`}
                    onToggle={() => onStashCollapsedChange(stash.id, !collapsed)}
                  />
                  <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
                    <StashIcon />
                  </span>
                  <Link
                    href={`/stashes/${stash.slug}`}
                    className="flex-1 truncate text-foreground hover:text-[var(--color-brand-700)]"
                  >
                    {stash.title}
                  </Link>
                </div>
                {!collapsed ? (
                  <div className="ml-2.5 space-y-0.5 border-l border-border pl-2">
                    {children.length === 0 ? (
                      <div className="px-2 py-1 text-[11px] italic text-muted">
                        no visible items
                      </div>
                    ) : (
                      children.map((item) => (
                        <StashTreeRow key={item.key} row={item} />
                      ))
                    )}
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    );
  }

  return (
    <details
      open={open}
      onToggle={(e) => onOpenChange(e.currentTarget.open)}
      className="group/section text-[13px]"
    >
      <summary
        onClick={(e) => {
          e.preventDefault();
          onOpenChange(!open);
        }}
        className="page-row flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-raised"
      >
        <Link
          href={`/workspaces/${workspace.id}/stashes`}
          onClick={(event) => {
            event.stopPropagation();
            onOpenChange(true);
          }}
          className="flex-1 truncate text-[11px] font-semibold uppercase tracking-wide text-muted hover:text-foreground"
        >
          Stashes
        </Link>
        <ChevronToggle open={open} onToggle={() => onOpenChange(!open)} hoverOnly />
      </summary>
      <div className="ml-3 space-y-0.5 border-l border-border pl-2">
        {nativeStashes.length === 0 && forkedStashes.length === 0 ? (
          <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
        ) : null}
        {renderStashGroup(null, nativeStashes, false)}
        {renderStashGroup("Forked stashes", forkedStashes, false)}
        <SectionAddRow label="New Stash" onClick={onAddStash} />
      </div>
    </details>
  );
}

function WorkspaceSwitcher({
  active,
  mine,
  shared,
}: {
  active: WorkspaceNode | null;
  mine: Workspace[];
  shared: Workspace[];
}) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(event: globalThis.MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label = active?.name ?? "Pick a workspace";
  const total = mine.length + shared.length;

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-[5px] bg-[var(--color-brand-600)] text-[11px] font-bold text-white">
          {(active?.name ?? "S").slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-[13.5px] font-semibold tracking-tight text-foreground">
            {label}
          </span>
          {active && (
            <span className="block truncate text-[10.5px] text-muted">
              {total} workspace{total === 1 ? "" : "s"}
            </span>
          )}
        </span>
        <svg
          className={"h-3.5 w-3.5 text-muted transition-transform " + (open ? "rotate-180" : "")}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 right-0 top-full z-40 mt-1 max-h-[60vh] overflow-y-auto rounded-md border border-border bg-base py-1 shadow-lg"
        >
          {mine.length > 0 && (
            <>
              <div className="px-3 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
                Your workspaces
              </div>
              {mine.map((w) => (
                <WorkspaceMenuItem
                  key={w.id}
                  workspace={w}
                  active={active?.id === w.id}
                  onClose={() => setOpen(false)}
                />
              ))}
            </>
          )}
          {shared.length > 0 && (
            <>
              <div className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted">
                Shared with you
              </div>
              {shared.map((w) => (
                <WorkspaceMenuItem
                  key={w.id}
                  workspace={w}
                  active={active?.id === w.id}
                  onClose={() => setOpen(false)}
                />
              ))}
            </>
          )}
          {mine.length === 0 && shared.length === 0 && (
            <div className="px-3 py-1.5 text-[12px] italic text-muted">
              No workspaces yet.
            </div>
          )}
          <div className="mt-1 border-t border-border pt-1">
            <Link
              href="/"
              onClick={() => setOpen(false)}
              className="block px-3 py-1.5 text-[12.5px] text-dim hover:bg-raised hover:text-foreground"
              role="menuitem"
            >
              + New or join workspace
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

function WorkspaceMenuItem({
  workspace,
  active,
  onClose,
}: {
  workspace: Workspace;
  active: boolean;
  onClose: () => void;
}) {
  return (
    <Link
      href={`/workspaces/${workspace.id}`}
      onClick={onClose}
      role="menuitem"
      className={
        "flex items-center gap-2 px-3 py-1.5 text-[13px] " +
        (active
          ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)]"
          : "text-foreground hover:bg-raised")
      }
    >
      <span
        className={
          "flex h-5 w-5 items-center justify-center rounded-[4px] text-[10px] font-bold text-white " +
          (active ? "bg-[var(--color-brand-700)]" : "bg-[var(--color-brand-600)]")
        }
      >
        {workspace.name.slice(0, 1).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium">{workspace.name}</span>
      {active && (
        <svg
          className="h-3.5 w-3.5 text-[var(--color-brand-700)]"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
    </Link>
  );
}

export default function AppSidebar({
  user,
  activeWorkspaceId,
}: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const shareModal = useShareModal();
  const userId = user?.id;
  const cachedWorkspaces = readCachedWorkspaces(userId);
  const activeTreeMatch = pathname.match(
    /^\/workspaces\/([^/]+)\/(sessions|folders|p|f|stashes)(?:\/|$)/
  );
  const activeTreeWorkspaceId = activeTreeMatch?.[1] ?? null;
  const activeTreeSection: SidebarSection | null =
    activeTreeMatch?.[2] === "sessions"
      ? "sessions"
      : activeTreeMatch?.[2] === "stashes"
        ? "stashes"
      : activeTreeMatch
        ? "files"
        : null;
  const routeWorkspaceId = pathname.match(/^\/workspaces\/([^/]+)/)?.[1] ?? null;
  // Persisted "last-viewed workspace" so navigation to non-workspace routes
  // (/stashes/{slug}, /discover, /activity) doesn't lose the workspace
  // context. Updated below whenever the route reveals an explicit workspace.
  const [lastWorkspaceId, setLastWorkspaceId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(LAST_WORKSPACE_KEY);
  });
  const currentWorkspaceId =
    activeWorkspaceId ?? routeWorkspaceId ?? lastWorkspaceId;
  const [mine, setMine] = useState<Workspace[]>(cachedWorkspaces?.mine ?? []);
  const [shared, setShared] = useState<Workspace[]>(cachedWorkspaces?.shared ?? []);

  useEffect(() => {
    if (!routeWorkspaceId) return;
    if (routeWorkspaceId === lastWorkspaceId) return;
    setLastWorkspaceId(routeWorkspaceId);
    if (typeof window !== "undefined") {
      localStorage.setItem(LAST_WORKSPACE_KEY, routeWorkspaceId);
    }
  }, [routeWorkspaceId, lastWorkspaceId]);
  const [openWorkspaces] = useState<Record<string, boolean>>(() =>
    readBooleanMap(OPEN_WORKSPACES_KEY)
  );
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() =>
    readBooleanMap(OPEN_SECTIONS_KEY)
  );
  const [spines, setSpines] = useState<Record<string, WorkspaceSidebar>>(() =>
    readCachedSidebars()
  );
  const [dropState, setDropState] = useState<SidebarDropState>({
    key: null,
    status: "idle",
    message: "",
  });
  const [pinnedState, setPinnedState] = useState<Record<string, { folders: string[]; files: string[] }>>(
    () => readPinnedMap()
  );
  const [pinnedLabelsState, setPinnedLabelsState] = useState<Record<string, PinnedLabels>>(
    () => readPinnedLabelMap()
  );
  const [collapsedStashes, setCollapsedStashes] = useState<Record<string, boolean>>(
    () => readBooleanMap(COLLAPSED_STASHES_KEY)
  );
  const [pageCreateWorkspaceId, setPageCreateWorkspaceId] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;

    getCachedWorkspaces(userId)
      .then((r) => {
        setMine(r.mine);
        setShared(r.shared);
      })
      .catch(() => {});
  }, [userId]);

  const setOpenSection = useCallback((
    workspaceId: string,
    section: SidebarSection,
    open: boolean
  ) => {
    setOpenSections((current) => {
      const next = { ...current, [sectionKey(workspaceId, section)]: open };
      writeBooleanMap(OPEN_SECTIONS_KEY, next);
      return next;
    });
  }, []);

  useEffect(() => {
    const workspaceIds = new Set<string>([
      ...Object.keys(openWorkspaces).filter((workspaceId) => openWorkspaces[workspaceId]),
      ...mine.map((workspace) => workspace.id),
      ...shared.map((workspace) => workspace.id),
    ]);

    if (activeTreeWorkspaceId) workspaceIds.add(activeTreeWorkspaceId);

    Array.from(workspaceIds)
      .filter((workspaceId) => !spines[workspaceId])
      .forEach((workspaceId) => {
        getCachedWorkspaceSidebar(workspaceId)
          .then((sp) => setSpines((all) => ({ ...all, [workspaceId]: sp })))
          .catch(() => {});
      });
  }, [activeTreeWorkspaceId, mine, shared, openWorkspaces, spines]);

  function sectionOpen(workspaceId: string, section: SidebarSection): boolean {
    // Explicit user preference (open or closed) wins. Otherwise default open.
    const explicit = openSections[sectionKey(workspaceId, section)];
    if (explicit !== undefined) return explicit;
    return true;
  }

  function getOpenSections(workspaceId: string): Record<SidebarSection, boolean> {
    return {
      sessions: sectionOpen(workspaceId, "sessions"),
      files: sectionOpen(workspaceId, "files"),
      stashes: sectionOpen(workspaceId, "stashes"),
    };
  }

  function handleSectionOpenChange(
    workspaceId: string,
    section: SidebarSection,
    open: boolean
  ) {
    const explicit = openSections[sectionKey(workspaceId, section)];
    const routeOpen =
      activeTreeWorkspaceId === workspaceId && activeTreeSection === section;
    if (open && routeOpen && explicit === undefined) return;
    setOpenSection(workspaceId, section, open);
  }

  function handleStashCollapsedChange(
    workspaceId: string,
    stashId: string,
    collapsed: boolean
  ) {
    setCollapsedStashes((current) => {
      const key = stashCollapseKey(workspaceId, stashId);
      const next = { ...current };
      if (collapsed) {
        next[key] = true;
      } else {
        delete next[key];
      }
      writeBooleanMap(COLLAPSED_STASHES_KEY, next);
      return next;
    });
  }

  function clearDropLater(workspaceId: string, section: DropSection) {
    window.setTimeout(() => {
      setDropState((current) =>
        current.key === dropKey(workspaceId, section)
          ? { key: null, status: "idle", message: "" }
          : current
      );
    }, 2500);
  }

  function handleDropHover(workspaceId: string, section: DropSection, active: boolean) {
    const key = dropKey(workspaceId, section);
    setDropState((current) => {
      if (!active && current.key === key && current.status === "over") {
        return { key: null, status: "idle", message: "" };
      }
      if (!active) return current;
      return {
        key,
        status: "over",
        message:
          section === "sessions"
            ? "Drop .JSONL transcript files"
            : "Drop files (any type)",
      };
    });
  }

  async function refreshSidebar(workspaceId: string) {
    const sidebar = await refreshWorkspaceSidebar(workspaceId);
    setSpines((all) => ({ ...all, [workspaceId]: sidebar }));
  }

  function handleAddSession(workspaceId: string) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".jsonl,application/jsonl,application/x-ndjson";
    input.multiple = true;
    input.onchange = () => {
      if (input.files) handleDropFiles(workspaceId, "sessions", input.files);
    };
    input.click();
  }

  function handleAddPage(workspaceId: string) {
    setPageCreateWorkspaceId(workspaceId);
  }

  async function handleCreatePage(workspaceId: string, name: string) {
    setDropState({
      key: dropKey(workspaceId, "files"),
      status: "saving",
      message: `Creating ${name}...`,
    });
    try {
      const page = await createPage(workspaceId, name);
      await refreshSidebar(workspaceId);
      setDropState({
        key: dropKey(workspaceId, "files"),
        status: "done",
        message: `Created ${page.name}.`,
      });
      clearDropLater(workspaceId, "files");
      setPageCreateWorkspaceId(null);
      router.push(`/workspaces/${workspaceId}/p/${page.id}`);
    } catch (error) {
      setDropState({
        key: dropKey(workspaceId, "files"),
        status: "error",
        message: error instanceof Error ? error.message : "Failed to create page",
      });
      clearDropLater(workspaceId, "files");
      throw error;
    }
  }

  function handleAddStash(workspaceId: string) {
    shareModal.open({ workspaceId, tab: "new" });
  }

  async function handleDropFiles(workspaceId: string, section: DropSection, files: FileList) {
    const list = Array.from(files);
    const key = dropKey(workspaceId, section);
    if (list.length === 0) return;

    if (section === "sessions") {
      const badFile = list.find((file) => !isJsonl(file));
      if (badFile) {
        setDropState({
          key,
          status: "error",
          message: "Sessions only accept .jsonl transcripts.",
        });
        clearDropLater(workspaceId, section);
        return;
      }

      const badSession = list.find((file) => !sessionIdFromFile(file));
      if (badSession) {
        setDropState({
          key,
          status: "error",
          message: "Transcript filename must include a session id.",
        });
        clearDropLater(workspaceId, section);
        return;
      }
    }

    setDropState({
      key,
      status: "saving",
      message: list.length === 1 ? `Uploading ${list[0].name}...` : `Uploading ${list.length} files...`,
    });

    try {
      if (section === "sessions") {
        for (const file of list) {
          await uploadTranscript(workspaceId, file, sessionIdFromFile(file), "manual-upload");
        }
      } else {
        for (const file of list) {
          await uploadFile(workspaceId, file);
        }
      }
      await refreshSidebar(workspaceId);
    } catch (error) {
      setDropState({
        key,
        status: "error",
        message: error instanceof Error ? error.message : "Upload failed",
      });
      clearDropLater(workspaceId, section);
      return;
    }

    setDropState({
      key,
      status: "done",
      message:
        section === "sessions"
          ? `${list.length} session${list.length === 1 ? "" : "s"} added.`
          : `${list.length} file${list.length === 1 ? "" : "s"} added.`,
    });
    clearDropLater(workspaceId, section);
  }

  function handlePinToggle(
    kind: PinKind,
    workspaceId: string,
    id: string,
    label?: string
  ) {
    setPinnedState((current) => {
      const workspacePins = current[workspaceId] ?? EMPTY_PIN_STATE;
      if (kind === "folder") {
        const isPinned = workspacePins.folders.includes(id);
        const nextFolders = isPinned
          ? workspacePins.folders.filter((value) => value !== id)
          : [...workspacePins.folders, id];
        const nextWorkspace = { ...workspacePins, folders: nextFolders };
        const nextState = { ...current, [workspaceId]: nextWorkspace };
        writePinnedMap(nextState);
        if (!isPinned && label) {
          setPinnedLabelsState((currentLabels) => {
            const nextLabels = {
              ...currentLabels,
              [workspaceId]: {
                ...(currentLabels[workspaceId] ?? { folders: {}, files: {} }),
                folders: {
                  ...(currentLabels[workspaceId]?.folders ?? {}),
                  [id]: label,
                },
              },
            };
            writePinnedLabelMap(nextLabels);
            return nextLabels;
          });
        }
        if (isPinned) {
          setPinnedLabelsState((currentLabels) => {
            const workspaceLabels = currentLabels[workspaceId];
            if (!workspaceLabels) return currentLabels;

            const nextFolders = { ...workspaceLabels.folders };
            delete nextFolders[id];
            const nextLabels = {
              ...currentLabels,
              [workspaceId]: {
                ...workspaceLabels,
                folders: nextFolders,
              },
            };
            writePinnedLabelMap(nextLabels);
            return nextLabels;
          });
        }
        return nextState;
      }

      const isPinned = workspacePins.files.includes(id);
      const nextFiles = isPinned
        ? workspacePins.files.filter((value) => value !== id)
        : [...workspacePins.files, id];
      const nextWorkspace = { ...workspacePins, files: nextFiles };
      const nextState = { ...current, [workspaceId]: nextWorkspace };
      writePinnedMap(nextState);
      if (!isPinned && label) {
        setPinnedLabelsState((currentLabels) => {
          const nextLabels = {
            ...currentLabels,
            [workspaceId]: {
              ...(currentLabels[workspaceId] ?? { folders: {}, files: {} }),
              files: {
                ...(currentLabels[workspaceId]?.files ?? {}),
                [id]: label,
              },
            },
          };
          writePinnedLabelMap(nextLabels);
          return nextLabels;
        });
      }
        if (isPinned) {
          setPinnedLabelsState((currentLabels) => {
            const workspaceLabels = currentLabels[workspaceId];
            if (!workspaceLabels) return currentLabels;

            const nextFiles = { ...workspaceLabels.files };
            delete nextFiles[id];
            const nextLabels = {
              ...currentLabels,
              [workspaceId]: {
                ...workspaceLabels,
                files: nextFiles,
              },
            };
            writePinnedLabelMap(nextLabels);
            return nextLabels;
          });
        }
      return nextState;
    });
  }

  function handleUnpinAll(workspaceId: string) {
      setPinnedState((current) => {
        const workspacePins = current[workspaceId];
        if (!workspacePins || (workspacePins.folders.length === 0 && workspacePins.files.length === 0)) {
          return current;
        }
        const nextState = {
          ...current,
          [workspaceId]: { folders: [], files: [] },
        };
        writePinnedMap(nextState);
        setPinnedLabelsState((currentLabels) => {
          const workspaceLabels = currentLabels[workspaceId];
          if (!workspaceLabels) return currentLabels;

          const nextLabels = {
            ...currentLabels,
            [workspaceId]: { folders: {}, files: {} },
          };
          writePinnedLabelMap(nextLabels);
          return nextLabels;
        });
      return nextState;
    });
  }

  useEffect(() => {
    setPinnedLabelsState((currentLabels) => {
      const nextLabels: Record<string, PinnedLabels> = { ...currentLabels };
      let changed = false;

      for (const [workspaceId, workspacePins] of Object.entries(pinnedState)) {
        const tree = spines[workspaceId]?.files;
        const folderById = new Map((tree?.folders ?? []).map((folder) => [folder.id, folder]));
        const fileById = new Map((tree?.files ?? []).map((file) => [file.id, file]));

        const workspaceLabels = nextLabels[workspaceId] ?? { folders: {}, files: {} };
        let workspaceChanged = false;
        const nextWorkspaceFolders = { ...workspaceLabels.folders };
        const nextWorkspaceFiles = { ...workspaceLabels.files };

        for (const folderId of workspacePins.folders) {
          if (nextWorkspaceFolders[folderId]) continue;

          const folderName = folderById.get(folderId)?.name;
          if (!folderName) continue;

          nextWorkspaceFolders[folderId] = folderName;
          workspaceChanged = true;
        }

        for (const fileId of workspacePins.files) {
          if (nextWorkspaceFiles[fileId]) continue;

          const fileName = fileById.get(fileId)?.name;
          if (!fileName) continue;

          nextWorkspaceFiles[fileId] = fileName;
          workspaceChanged = true;
        }

        if (!workspaceChanged) continue;

        nextLabels[workspaceId] = {
          folders: nextWorkspaceFolders,
          files: nextWorkspaceFiles,
        };
        changed = true;
      }

      if (!changed) return currentLabels;
      writePinnedLabelMap(nextLabels);
      return nextLabels;
    });
  }, [pinnedState, spines]);

  // The sidebar always renders a single workspace context. Priority:
  // (1) the workspace in the current URL, (2) the first owned workspace,
  // (3) the first shared workspace. Switching via the WorkspaceSwitcher
  // navigates to /workspaces/{id} which then drives this back through the URL.
  const activeWorkspace: WorkspaceNode | null =
    (currentWorkspaceId &&
      (mine.find((w) => w.id === currentWorkspaceId) ??
        (shared.find((w) => w.id === currentWorkspaceId)
          ? { ...shared.find((w) => w.id === currentWorkspaceId)!, shared: true }
          : null))) ||
    mine[0] ||
    (shared[0] ? { ...shared[0], shared: true } : null);

  return (
    <>
    <aside className="scroll-thin overflow-y-auto border-r border-border bg-surface">
      <div className="px-2 pt-2">
        <WorkspaceSwitcher
          active={activeWorkspace}
          mine={mine}
          shared={shared}
        />
      </div>

      <nav className="px-2 pt-2 text-[13px]">
        <NavRow
          href={activeWorkspace ? `/workspaces/${activeWorkspace.id}` : "/"}
          icon={<StashIcon />}
          label="Home"
          active={
            activeWorkspace
              ? pathname === `/workspaces/${activeWorkspace.id}`
              : pathname === "/"
          }
        />
        <NavRow
          href="/discover"
          icon={<DiscoverIcon />}
          label="Discover"
          active={pathname.startsWith("/discover")}
        />
        <NavRow
          href="/activity"
          icon={<ActivityIcon />}
          label="Activity"
          active={pathname.startsWith("/activity")}
        />
      </nav>

      <nav className="mt-4 px-1 text-[13.5px]">
        {activeWorkspace ? (
          <WorkspaceTree
            key={activeWorkspace.id}
            workspace={activeWorkspace}
            spine={spines[activeWorkspace.id] ?? null}
            pathname={pathname}
            openSections={getOpenSections(activeWorkspace.id)}
            onSectionOpenChange={(section, open) =>
              handleSectionOpenChange(activeWorkspace.id, section, open)
            }
            dropState={dropState}
            onDropFiles={handleDropFiles}
            onDropHover={handleDropHover}
            pinnedFolders={pinnedState[activeWorkspace.id]?.folders ?? EMPTY_PIN_STATE.folders}
            pinnedFiles={pinnedState[activeWorkspace.id]?.files ?? EMPTY_PIN_STATE.files}
            pinnedLabels={pinnedLabelsState[activeWorkspace.id] ?? { folders: {}, files: {} }}
            collapsedStashes={collapsedStashes}
            onPinToggle={(kind, id, label) => handlePinToggle(kind, activeWorkspace.id, id, label)}
            onUnpinAll={handleUnpinAll}
            onStashCollapsedChange={handleStashCollapsedChange}
            onAddSession={handleAddSession}
            onAddPage={handleAddPage}
            onAddStash={handleAddStash}
          />
        ) : (
          <div className="px-3 py-1.5 text-[12px] italic text-muted">
            No workspaces yet.
          </div>
        )}
      </nav>

      <div className="mt-6 border-t border-border px-2 py-2">
        <NavRow href="/docs" icon={<HelpIcon />} label="Docs" active={pathname.startsWith("/docs")} />
        {activeWorkspace ? (
          <NavRow
            href={`/workspaces/${activeWorkspace.id}/settings`}
            icon={<SettingsIcon />}
            label="Settings"
            active={pathname === `/workspaces/${activeWorkspace.id}/settings`}
          />
        ) : (
          <DisabledNavRow icon={<SettingsIcon />} label="Settings" />
        )}
      </div>
    </aside>
    {pageCreateWorkspaceId ? (
      <CreatePageModal
        onClose={() => setPageCreateWorkspaceId(null)}
        onCreate={(name) => handleCreatePage(pageCreateWorkspaceId, name)}
      />
    ) : null}
    </>
  );
}
