"use client";

import Link from "next/link";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import {
  getCachedWorkspaceSidebar,
  getCachedWorkspaces,
  readCachedSidebars,
  readCachedWorkspaces,
  subscribeToSidebarRefresh,
} from "../lib/stashNavigationCache";
import type { WorkspaceSidebar, WorkspaceSidebarSession } from "../lib/api";
import type { User, Workspace } from "../lib/types";
import { usePins } from "../lib/pins";
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
  TrashIcon,
  WorkspaceIcon,
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

const LAST_WORKSPACE_KEY = "stash_sidebar_last_workspace";
const OPEN_SECTIONS_KEY = "stash_sidebar_open_sections";

function readOpenSections(): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  const raw = window.localStorage.getItem(OPEN_SECTIONS_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    window.localStorage.removeItem(OPEN_SECTIONS_KEY);
    return {};
  }
}

function writeOpenSections(map: Record<string, boolean>) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(OPEN_SECTIONS_KEY, JSON.stringify(map));
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
        "page-row group/nav flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1 text-[13px] transition-colors " +
        (active
          ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)]"
          : "text-dim hover:bg-raised hover:text-foreground")
      }
      onClick={onClick}
      onContextMenu={onContextMenu}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center text-[14px]">{icon}</span>
      <span className="min-w-0 flex-1 truncate" title={label}>{label}</span>
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

// Each pinned dropdown row resolves to a concrete destination.
interface PinnedRow {
  key: string;
  href: string;
  label: string;
  icon: ReactNode;
  active: boolean;
}

function fileIconClass(contentType: string | undefined): string {
  if (contentType?.includes("pdf")) return "text-rose-500";
  if (contentType?.includes("csv")) return "text-emerald-600";
  if (contentType?.includes("html")) return "text-amber-600";
  return "text-muted";
}

function cleanSessionTitle(title: string): string {
  return title
    .replace(/^\s*title:\s*/i, "")
    .replace(/^\s{0,3}#{1,6}\s*/, "")
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .trim();
}

function sessionLabelForSidebar(session: WorkspaceSidebarSession): string {
  const raw = (session.title || session.session_id).trim();
  return cleanSessionTitle(raw) || session.session_id;
}

function resolveFilePins(
  ids: string[],
  spine: WorkspaceSidebar | null,
  workspaceId: string,
  pathname: string,
): PinnedRow[] {
  if (!spine) return [];
  const folders = new Map(spine.files.folders.map((f) => [f.id, f]));
  const pages = new Map(spine.files.pages.map((p) => [p.id, p]));
  const files = new Map(spine.files.files.map((f) => [f.id, f]));
  const rows: PinnedRow[] = [];
  for (const id of ids) {
    const folder = folders.get(id);
    if (folder) {
      const href = `/workspaces/${workspaceId}/folders/${id}`;
      rows.push({ key: id, href, label: folder.name, icon: <FolderIcon />, active: pathname === href });
      continue;
    }
    const page = pages.get(id);
    if (page) {
      const href = `/workspaces/${workspaceId}/p/${id}`;
      rows.push({
        key: id,
        href,
        label: page.name,
        icon: <span className="text-muted"><PageIcon /></span>,
        active: pathname === href,
      });
      continue;
    }
    const file = files.get(id);
    if (file) {
      const csv = !!(file.content_type?.includes("csv") && file.linked_table_id);
      const href = csv
        ? `/tables/${file.linked_table_id}?workspaceId=${workspaceId}`
        : `/workspaces/${workspaceId}/f/${id}`;
      rows.push({
        key: id,
        href,
        label: file.name,
        icon: <span className={fileIconClass(file.content_type)}>{csv ? <TableIcon /> : <FileIcon />}</span>,
        active: pathname.includes(`/f/${id}`),
      });
    }
  }
  return rows;
}

function resolveSessionPins(
  ids: string[],
  spine: WorkspaceSidebar | null,
  workspaceId: string,
  pathname: string,
): PinnedRow[] {
  if (!spine) return [];
  const bySessionId = new Map(spine.sessions.map((s) => [s.session_id, s]));
  const rows: PinnedRow[] = [];
  for (const id of ids) {
    const session = bySessionId.get(id);
    if (!session) continue;
    const href = `/workspaces/${workspaceId}/sessions/${encodeURIComponent(id)}`;
    rows.push({
      key: id,
      href,
      label: sessionLabelForSidebar(session),
      icon: <span className="text-muted"><SessionsIcon /></span>,
      active: pathname === href,
    });
  }
  return rows;
}

function resolveStashPins(
  ids: string[],
  spine: WorkspaceSidebar | null,
  pathname: string,
): PinnedRow[] {
  if (!spine?.stashes) return [];
  const byId = new Map(spine.stashes.map((s) => [s.id, s]));
  const rows: PinnedRow[] = [];
  for (const id of ids) {
    const stash = byId.get(id);
    if (!stash) continue;
    const href = `/stashes/${stash.slug}`;
    rows.push({
      key: id,
      href,
      label: stash.title,
      icon: <span className="text-muted"><StashIcon /></span>,
      active: pathname === href || pathname.startsWith(`${href}/`),
    });
  }
  return rows;
}

function ChevronToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
      className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted transition-colors hover:bg-raised hover:text-foreground"
      aria-expanded={open}
      aria-label="Toggle section"
    >
      <svg
        className={"h-3 w-3" + (open ? " rotate-90" : "")}
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

// A collapsible section whose header links to the list page and whose body
// shows only the items the user has pinned for that type.
function PinnedSection({
  label,
  href,
  headerActive,
  items,
  open,
  onToggle,
}: {
  label: string;
  href: string;
  headerActive: boolean;
  items: PinnedRow[];
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div>
      {/* Two distinct targets: the chevron only toggles the section (its own
          hover affordance), the label link only navigates into the list page
          (its own hover affordance). The row itself has no hover state so the
          two actions never read as one. */}
      <div className="flex items-center gap-0.5 px-1">
        <ChevronToggle open={open} onToggle={onToggle} />
        <Link
          href={href}
          className={
            "flex min-w-0 flex-1 items-center gap-1.5 rounded-md px-1.5 py-1 text-[11px] font-semibold uppercase tracking-wide transition-colors " +
            (headerActive
              ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)]"
              : "text-muted hover:bg-raised hover:text-foreground")
          }
        >
          <span className="min-w-0 flex-1 truncate">{label}</span>
          {items.length > 0 && (
            <span className="text-[10px] tabular-nums text-muted">{items.length}</span>
          )}
        </Link>
      </div>
      {open && (
        <div className="ml-3 space-y-0.5 border-l border-border pl-2">
          {items.length === 0 ? (
            <div className="px-2 py-1 text-[11px] italic text-muted">
              No pinned {label.toLowerCase()}
            </div>
          ) : (
            items.map((row) => (
              <NavRow
                key={row.key}
                href={row.href}
                icon={row.icon}
                label={row.label}
                active={row.active}
              />
            ))
          )}
        </div>
      )}
    </div>
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
        <span className="flex h-6 w-6 items-center justify-center rounded-[5px] bg-[var(--color-brand-100)] text-[var(--color-brand-700)]">
          <WorkspaceIcon className="text-[16px]" />
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
        className="flex h-5 w-5 items-center justify-center rounded-[4px] bg-[var(--color-brand-100)] text-[var(--color-brand-700)]"
      >
        <WorkspaceIcon className="text-[13px]" />
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
  const userId = user?.id;
  const cachedWorkspaces = readCachedWorkspaces(userId);
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
  // Sidebar spine resolves pinned ids to names/routes for the dropdowns, and
  // the active stash's slug for the footer Settings link.
  const [spines, setSpines] = useState<Record<string, WorkspaceSidebar>>(() =>
    readCachedSidebars()
  );

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
  const activeWorkspaceKey = activeWorkspace?.id ?? "";

  const stashPins = usePins("stashes", activeWorkspaceKey);
  const sessionPins = usePins("sessions", activeWorkspaceKey);
  const filePins = usePins("files", activeWorkspaceKey);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() =>
    readOpenSections()
  );

  function toggleSection(section: string) {
    setOpenSections((current) => {
      const key = `${activeWorkspaceKey}:${section}`;
      const next = { ...current, [key]: !(current[key] ?? true) };
      writeOpenSections(next);
      return next;
    });
  }

  function sectionOpen(section: string): boolean {
    return openSections[`${activeWorkspaceKey}:${section}`] ?? true;
  }

  useEffect(() => {
    if (!routeWorkspaceId) return;
    if (routeWorkspaceId === lastWorkspaceId) return;
    setLastWorkspaceId(routeWorkspaceId);
    if (typeof window !== "undefined") {
      localStorage.setItem(LAST_WORKSPACE_KEY, routeWorkspaceId);
    }
  }, [routeWorkspaceId, lastWorkspaceId]);

  useEffect(() => {
    if (!userId) return;
    getCachedWorkspaces(userId)
      .then((r) => {
        setMine(r.mine);
        setShared(r.shared);
      })
      .catch(() => {});
  }, [userId]);

  // Load the active workspace's spine so the pinned dropdowns can resolve.
  useEffect(() => {
    if (!activeWorkspaceKey) return;
    if (spines[activeWorkspaceKey]) return;
    getCachedWorkspaceSidebar(activeWorkspaceKey)
      .then((sp) => setSpines((all) => ({ ...all, [activeWorkspaceKey]: sp })))
      .catch(() => {});
  }, [activeWorkspaceKey, spines]);

  useEffect(() => {
    return subscribeToSidebarRefresh((workspaceId, sidebar) => {
      setSpines((all) => ({ ...all, [workspaceId]: sidebar }));
    });
  }, []);

  const spine = activeWorkspace ? spines[activeWorkspace.id] ?? null : null;
  const stashRows = useMemo(
    () => resolveStashPins(stashPins.pinnedIds, spine, pathname),
    [stashPins.pinnedIds, spine, pathname],
  );
  const sessionRows = useMemo(
    () => resolveSessionPins(sessionPins.pinnedIds, spine, activeWorkspaceKey, pathname),
    [sessionPins.pinnedIds, spine, activeWorkspaceKey, pathname],
  );
  const fileRows = useMemo(
    () => resolveFilePins(filePins.pinnedIds, spine, activeWorkspaceKey, pathname),
    [filePins.pinnedIds, spine, activeWorkspaceKey, pathname],
  );

  const activeStashSlug = pathname.match(/^\/stashes\/([^/?#]+)/)?.[1] ?? null;
  const activeStash =
    activeWorkspace && activeStashSlug
      ? spines[activeWorkspace.id]?.stashes?.find((stash) => stash.slug === activeStashSlug)
      : null;
  const settingsHref = activeStash
    ? `/stashes/${activeStash.slug}/settings`
    : activeWorkspace
      ? `/workspaces/${activeWorkspace.id}/settings`
      : "";
  const settingsActive = activeStash
    ? pathname === `/stashes/${activeStash.slug}/settings`
    : activeWorkspace
      ? pathname === `/workspaces/${activeWorkspace.id}/settings`
      : false;

  return (
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
        {activeWorkspace ? (
          <NavRow
            href={`/workspaces/${activeWorkspace.id}/members`}
            icon={<PersonIcon />}
            label="Members"
            active={pathname === `/workspaces/${activeWorkspace.id}/members`}
          />
        ) : null}
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

      <nav className="mt-4 space-y-0.5 px-2 text-[13px]">
        {activeWorkspace ? (
          <>
            <PinnedSection
              label="Stashes"
              href={`/workspaces/${activeWorkspace.id}/stashes`}
              headerActive={
                pathname.startsWith(`/workspaces/${activeWorkspace.id}/stashes`) ||
                pathname.startsWith("/stashes/")
              }
              items={stashRows}
              open={sectionOpen("stashes")}
              onToggle={() => toggleSection("stashes")}
            />
            <PinnedSection
              label="Sessions"
              href={`/workspaces/${activeWorkspace.id}/sessions`}
              headerActive={pathname.startsWith(`/workspaces/${activeWorkspace.id}/sessions`)}
              items={sessionRows}
              open={sectionOpen("sessions")}
              onToggle={() => toggleSection("sessions")}
            />
            <PinnedSection
              label="Files"
              href={`/workspaces/${activeWorkspace.id}/files`}
              headerActive={
                !!pathname.match(
                  new RegExp(`^/workspaces/${activeWorkspace.id}/(files|folders|p|f)(?:/|$)`),
                )
              }
              items={fileRows}
              open={sectionOpen("files")}
              onToggle={() => toggleSection("files")}
            />
            <NavRow
              href={`/workspaces/${activeWorkspace.id}/trash`}
              icon={<TrashIcon />}
              label="Trash"
              active={pathname === `/workspaces/${activeWorkspace.id}/trash`}
            />
          </>
        ) : (
          <div className="px-3 py-1.5 text-[12px] italic text-muted">
            No workspaces yet.
          </div>
        )}
      </nav>

      <div className="mt-6 border-t border-border px-2 py-2">
        <a
          href="https://joinstash.ai/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="page-row group/nav flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1 text-[13px] transition-colors text-dim hover:bg-raised hover:text-foreground"
        >
          <span className="flex h-4 w-4 shrink-0 items-center justify-center text-[14px]"><HelpIcon /></span>
          <span className="min-w-0 flex-1 truncate">Docs</span>
        </a>
        {activeWorkspace ? (
          <NavRow
            href={settingsHref}
            icon={<SettingsIcon />}
            label="Settings"
            active={settingsActive}
          />
        ) : (
          <DisabledNavRow icon={<SettingsIcon />} label="Settings" />
        )}
      </div>
    </aside>
  );
}
