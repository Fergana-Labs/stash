"use client";

import Link from "next/link";
import {
  useEffect,
  useMemo,
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
import {
  listWorkspaceSources,
  type WorkspaceSidebar,
  type WorkspaceSidebarSession,
  type WorkspaceSource,
} from "../lib/api";
import type { User, Workspace } from "../lib/types";
import { usePins } from "../lib/pins";
import {
  ActivityIcon,
  DiscoverIcon,
  FileIcon,
  FolderIcon,
  HelpIcon,
  PageIcon,
  SessionsIcon,
  SettingsIcon,
  StashIcon,
  TableIcon,
  TrashIcon,
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

function resolveCartridgePins(
  ids: string[],
  spine: WorkspaceSidebar | null,
  pathname: string,
): PinnedRow[] {
  if (!spine?.cartridges) return [];
  const byId = new Map(spine.cartridges.map((s) => [s.id, s]));
  const rows: PinnedRow[] = [];
  for (const id of ids) {
    const stash = byId.get(id);
    if (!stash) continue;
    const href = `/cartridges/${stash.slug}`;
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


export default function AppSidebar({
  user,
  activeWorkspaceId,
}: AppSidebarProps) {
  const pathname = usePathname();
  const userId = user?.id;
  const cachedWorkspaces = readCachedWorkspaces(userId);
  const routeWorkspaceId = pathname.match(/^\/workspaces\/([^/]+)/)?.[1] ?? null;
  // Persisted "last-viewed workspace" so navigation to non-workspace routes
  // (/cartridges/{slug}, /discover, /activity) doesn't lose the workspace
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
  // Connected sources (GitHub/Drive/Notion/Slack/Granola) for the active
  // workspace, keyed by workspace id. User-scoped — only the viewer's own.
  const [sourceMap, setSourceMap] = useState<Record<string, WorkspaceSource[]>>({});

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

  const stashPins = usePins("cartridges", activeWorkspaceKey);
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

  // Load the active workspace's connected sources for the Sources section.
  useEffect(() => {
    if (!activeWorkspaceKey) return;
    listWorkspaceSources(activeWorkspaceKey)
      .then((sources) => setSourceMap((all) => ({ ...all, [activeWorkspaceKey]: sources })))
      .catch(() => {});
  }, [activeWorkspaceKey]);

  const spine = activeWorkspace ? spines[activeWorkspace.id] ?? null : null;
  const stashRows = useMemo(
    () => resolveCartridgePins(stashPins.pinnedIds, spine, pathname),
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
  const sourceRows = useMemo<PinnedRow[]>(() => {
    if (!activeWorkspaceKey) return [];
    const sources = sourceMap[activeWorkspaceKey] ?? [];
    // Connected sources are managed (reconnect, sync, remove) on the
    // integrations settings page — the same target as "Add a new source".
    return sources.map((s) => ({
      key: s.source,
      href: "/settings/integrations",
      label: s.display_name,
      icon: <span className="inline-block h-1.5 w-1.5 rounded-full bg-foreground/40" />,
      active: false,
    }));
  }, [activeWorkspaceKey, sourceMap]);

  const activeCartridgeSlug = pathname.match(/^\/cartridges\/([^/?#]+)/)?.[1] ?? null;
  const activeCartridge =
    activeWorkspace && activeCartridgeSlug
      ? spines[activeWorkspace.id]?.cartridges?.find((stash) => stash.slug === activeCartridgeSlug)
      : null;
  const settingsHref = activeCartridge
    ? `/cartridges/${activeCartridge.slug}/settings`
    : activeWorkspace
      ? `/workspaces/${activeWorkspace.id}/settings`
      : "";
  const settingsActive = activeCartridge
    ? pathname === `/cartridges/${activeCartridge.slug}/settings`
    : activeWorkspace
      ? pathname === `/workspaces/${activeWorkspace.id}/settings`
      : false;

  return (
    <aside className="scroll-thin overflow-y-auto border-r border-border bg-surface">
      <div className="px-3 pt-3 pb-1">
        <div className="truncate text-[14px] font-semibold text-foreground">
          {user?.display_name || user?.name || "You"}
        </div>
        <div className="text-[11px] text-muted">Personal</div>
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
            href={`/workspaces/${activeWorkspace.id}/agents`}
            icon={<span aria-hidden>✦</span>}
            label="Agents"
            active={pathname.startsWith(`/workspaces/${activeWorkspace.id}/agents`)}
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
              label="Cartridges"
              href={`/workspaces/${activeWorkspace.id}/cartridges`}
              headerActive={
                pathname.startsWith(`/workspaces/${activeWorkspace.id}/cartridges`) ||
                pathname.startsWith("/cartridges/")
              }
              items={stashRows}
              open={sectionOpen("cartridges")}
              onToggle={() => toggleSection("cartridges")}
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
            <PinnedSection
              label="Sources"
              href="/settings/integrations"
              headerActive={pathname.startsWith("/settings/integrations")}
              items={sourceRows}
              open={sectionOpen("sources")}
              onToggle={() => toggleSection("sources")}
            />
            <NavRow
              href="/settings/integrations"
              icon={<span aria-hidden>＋</span>}
              label="Add a new source"
              active={false}
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
