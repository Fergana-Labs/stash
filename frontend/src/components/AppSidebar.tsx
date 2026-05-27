"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { usePathname } from "next/navigation";
import {
  getCachedWorkspaceSidebar,
  getCachedWorkspaces,
  readCachedSidebars,
  readCachedWorkspaces,
  subscribeToSidebarRefresh,
} from "../lib/stashNavigationCache";
import type { WorkspaceSidebar } from "../lib/api";
import type { User, Workspace } from "../lib/types";
import {
  ActivityIcon,
  DiscoverIcon,
  FolderIcon,
  HelpIcon,
  PersonIcon,
  SessionsIcon,
  SettingsIcon,
  StashIcon,
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

// The workspace's content lives on dedicated list pages now (Stashes,
// Sessions, Files). The sidebar links straight into those pages instead of
// expanding inline trees, keeping navigation flat and the list pages the one
// place to browse.
function WorkspaceNav({
  workspace,
  pathname,
}: {
  workspace: WorkspaceNode;
  pathname: string;
}) {
  const base = `/workspaces/${workspace.id}`;
  const stashesActive =
    pathname.startsWith(`${base}/stashes`) || pathname.startsWith("/stashes/");
  const sessionsActive = pathname.startsWith(`${base}/sessions`);
  const filesActive = !!pathname.match(
    new RegExp(`^/workspaces/${workspace.id}/(files|folders|p|f)(?:/|$)`),
  );

  return (
    <div className="space-y-0.5">
      <NavRow
        href={`${base}/stashes`}
        icon={<StashIcon />}
        label="Stashes"
        active={stashesActive}
      />
      <NavRow
        href={`${base}/sessions`}
        icon={<SessionsIcon />}
        label="Sessions"
        active={sessionsActive}
      />
      <NavRow
        href={`${base}/files`}
        icon={<FolderIcon />}
        label="Files"
        active={filesActive}
      />
      <NavRow
        href={`${base}/trash`}
        icon={<TrashIcon />}
        label="Trash"
        active={pathname === `${base}/trash`}
      />
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
  // Sidebar spine is only used now to resolve the active stash's slug so the
  // footer Settings link can point at stash settings when viewing a stash.
  const [spines, setSpines] = useState<Record<string, WorkspaceSidebar>>(() =>
    readCachedSidebars()
  );

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

  const onStashRoute = pathname.startsWith("/stashes/");

  useEffect(() => {
    if (!onStashRoute || !currentWorkspaceId) return;
    if (spines[currentWorkspaceId]) return;
    getCachedWorkspaceSidebar(currentWorkspaceId)
      .then((sp) => setSpines((all) => ({ ...all, [currentWorkspaceId]: sp })))
      .catch(() => {});
  }, [onStashRoute, currentWorkspaceId, spines]);

  useEffect(() => {
    return subscribeToSidebarRefresh((workspaceId, sidebar) => {
      setSpines((all) => ({ ...all, [workspaceId]: sidebar }));
    });
  }, []);

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

      <nav className="mt-4 px-2 text-[13px]">
        {activeWorkspace ? (
          <>
            <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
              Workspace
            </div>
            <WorkspaceNav workspace={activeWorkspace} pathname={pathname} />
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
