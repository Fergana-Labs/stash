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
} from "../lib/skillNavigationCache";
import {
  listWorkspaceSources,
  type WorkspaceSidebar,
  type WorkspaceSource,
} from "../lib/api";
import type { User, Workspace } from "../lib/types";
import AddSourceModal from "./integrations/AddSourceModal";
import { connectorIcon, labelForProvider, providerForSourceType } from "./integrations/connectors";
import {
  ActivityIcon,
  FileIcon,
  HelpIcon,
  SessionsIcon,
  SettingsIcon,
  SkillIcon,
  TrashIcon,
} from "./SkillIcons";

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
const EXTERNAL_SOURCES_COLLAPSED_KEY = "stash_external_sources_collapsed";

// A colored dot per source type, so the grouped Sources list reads as a set of
// equal peers (matching the mockup). Falls back to neutral.
const SOURCE_DOT: Record<string, string> = {
  github_repo: "#111111",
  google_drive: "#16a34a",
  notion: "#000000",
  slack: "#4a154b",
  granola: "#e0700f",
  jira_project: "#2563eb",
  asana_project: "#f06a6a",
  gong_calls: "#7c3aed",
  snowflake: "#29b5e8",
  twitter: "#0f1419",
};

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

function SourceDot({ color }: { color: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 rounded-full"
      style={{ background: color }}
    />
  );
}

// A resolved row in the flat Sources list.
interface SourceRow {
  key: string;
  href: string;
  label: string;
  icon: ReactNode;
  active: boolean;
}

export default function AppSidebar({
  user,
  activeWorkspaceId,
}: AppSidebarProps) {
  const pathname = usePathname();
  const userId = user?.id;
  const [addSourceOpen, setAddSourceOpen] = useState(false);
  const cachedWorkspaces = readCachedWorkspaces(userId);
  const routeWorkspaceId = pathname.match(/^\/workspaces\/([^/]+)/)?.[1] ?? null;
  // Persisted "last-viewed workspace" so navigation to non-workspace routes
  // (/skills/{slug}, /discover, /activity) doesn't lose the workspace
  // context. Updated below whenever the route reveals an explicit workspace.
  const [lastWorkspaceId, setLastWorkspaceId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(LAST_WORKSPACE_KEY);
  });
  const currentWorkspaceId =
    activeWorkspaceId ?? routeWorkspaceId ?? lastWorkspaceId;
  const [mine, setMine] = useState<Workspace[]>(cachedWorkspaces?.mine ?? []);
  const [shared, setShared] = useState<Workspace[]>(cachedWorkspaces?.shared ?? []);
  // Spine resolves the active skill's slug for the footer Settings link.
  const [spines, setSpines] = useState<Record<string, WorkspaceSidebar>>(() =>
    readCachedSidebars()
  );
  // Connected sources (GitHub/Drive/Gmail/Notion/Slack/Granola) for the active
  // workspace, keyed by workspace id. User-scoped — only the viewer's own.
  const [sourceMap, setSourceMap] = useState<Record<string, WorkspaceSource[]>>({});
  // Collapses only the connected external sources; the native Sessions,
  // Files, and Skills rows stay visible.
  const [externalCollapsed, setExternalCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(EXTERNAL_SOURCES_COLLAPSED_KEY) === "1";
  });

  function toggleExternalCollapsed() {
    const next = !externalCollapsed;
    setExternalCollapsed(next);
    localStorage.setItem(EXTERNAL_SOURCES_COLLAPSED_KEY, next ? "1" : "0");
  }

  // The sidebar always renders a single workspace context. Priority:
  // (1) the workspace in the current URL, (2) the first owned workspace,
  // (3) the first shared workspace.
  const activeWorkspace: WorkspaceNode | null =
    (currentWorkspaceId &&
      (mine.find((w) => w.id === currentWorkspaceId) ??
        (shared.find((w) => w.id === currentWorkspaceId)
          ? { ...shared.find((w) => w.id === currentWorkspaceId)!, shared: true }
          : null))) ||
    mine[0] ||
    (shared[0] ? { ...shared[0], shared: true } : null);
  const activeWorkspaceKey = activeWorkspace?.id ?? "";

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

  // Load the active workspace's spine (for the active-skill slug).
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

  // Load the active workspace's connected sources for the Sources list.
  useEffect(() => {
    if (!activeWorkspaceKey) return;
    listWorkspaceSources(activeWorkspaceKey)
      .then((sources) => setSourceMap((all) => ({ ...all, [activeWorkspaceKey]: sources })))
      .catch(() => {});
  }, [activeWorkspaceKey]);

  // The Sources list: the native sources always visible, then the user's
  // connected external sources behind a collapsible "External" header.
  // Connected sources are managed on the integrations settings page.
  const sourceRows = useMemo<{ native: SourceRow[]; connected: SourceRow[] }>(() => {
    if (!activeWorkspaceKey) return { native: [], connected: [] };
    const ws = activeWorkspaceKey;
    // Canonical item paths (/p, /f, /sessions) carry no workspace; they
    // count as active because the sidebar only renders them for the
    // workspace the open item resolved to.
    const filesActive =
      !!pathname.match(new RegExp(`^/workspaces/${ws}/(files|folders)(?:/|$)`)) ||
      !!pathname.match(/^\/(p|f)\//);
    const sessionsActive =
      pathname.startsWith(`/workspaces/${ws}/sessions`) ||
      pathname.startsWith("/sessions/");
    const skillsActive =
      pathname.startsWith(`/workspaces/${ws}/skills`) ||
      pathname.startsWith("/skills/");
    const native: SourceRow[] = [
      {
        key: "sessions",
        href: `/workspaces/${ws}/sessions`,
        label: "Agent Sessions",
        icon: <span className="text-muted"><SessionsIcon /></span>,
        active: sessionsActive,
      },
      {
        key: "files",
        href: `/workspaces/${ws}/files`,
        label: "Files",
        icon: <span className="text-muted"><FileIcon /></span>,
        active: filesActive,
      },
      {
        key: "skills",
        href: `/workspaces/${ws}/skills`,
        label: "Skills",
        icon: <span aria-hidden>❏</span>,
        active: skillsActive,
      },
    ];
    // One row per INTEGRATION (provider), not per source: collapse the
    // workspace's connected sources to their distinct providers. The dot color
    // comes from a representative source type of that provider.
    const seen = new Set<string>();
    const connected: SourceRow[] = [];
    for (const s of sourceMap[ws] ?? []) {
      const provider = providerForSourceType[s.type] ?? s.type;
      if (seen.has(provider)) continue;
      seen.add(provider);
      const logo = connectorIcon(provider);
      connected.push({
        key: provider,
        href: `/workspaces/${ws}/integrations/${provider}`,
        label: labelForProvider(provider),
        icon: logo ? (
          <span className="flex h-4 w-4 items-center justify-center [&_img]:h-4 [&_img]:w-4 [&_svg]:h-4 [&_svg]:w-4">
            {logo}
          </span>
        ) : (
          <SourceDot color={SOURCE_DOT[s.type] ?? "rgba(0,0,0,0.4)"} />
        ),
        active: pathname.startsWith(`/workspaces/${ws}/integrations/${provider}`),
      });
    }
    return { native, connected };
  }, [activeWorkspaceKey, sourceMap, pathname]);

  const activeSkillSlug = pathname.match(/^\/skills\/([^/?#]+)/)?.[1] ?? null;
  const activeSkill =
    activeWorkspace && activeSkillSlug
      ? spines[activeWorkspace.id]?.skills?.find((skill) => skill.slug === activeSkillSlug)
      : null;
  // Workspace settings now live on the unified /settings page; only Skills
  // keep their own settings route.
  const settingsHref = activeSkill
    ? `/skills/${activeSkill.slug}/settings`
    : "/settings";
  const settingsActive = activeSkill
    ? pathname === `/skills/${activeSkill.slug}/settings`
    : pathname === "/settings";

  return (
    <>
    <aside className="scroll-thin h-full overflow-y-auto border-r border-border bg-surface">
      <div className="px-3 pt-3 pb-1">
        <div className="truncate text-[14px] font-semibold text-foreground">
          {user?.display_name || user?.name || "You"}
        </div>
      </div>

      <nav className="px-2 pt-2 text-[13px]">
        <NavRow
          href={activeWorkspace ? `/workspaces/${activeWorkspace.id}` : "/"}
          icon={<SkillIcon />}
          label="Home"
          active={
            activeWorkspace
              ? pathname === `/workspaces/${activeWorkspace.id}`
              : pathname === "/"
          }
        />
        {/* "Your brain" is the revamped activity view — your accumulated
            knowledge, status, and newsfeed. Global (workspace-resolved within
            the page), so it sits up top next to Home. */}
        <NavRow
          href="/activity"
          icon={<ActivityIcon />}
          label="Your brain"
          active={pathname.startsWith("/activity")}
        />
        {activeWorkspace ? (
          <NavRow
            href={`/workspaces/${activeWorkspace.id}/agents`}
            icon={<span aria-hidden>✦</span>}
            label="Agents"
            active={pathname.startsWith(`/workspaces/${activeWorkspace.id}/agents`)}
          />
        ) : null}
      </nav>

      {activeWorkspace ? (
        <nav className="mt-4 px-2 text-[13px]">
          <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
            Sources
          </div>
          {sourceRows.native.map((row) => (
            <NavRow
              key={row.key}
              href={row.href}
              icon={row.icon}
              label={row.label}
              active={row.active}
            />
          ))}
          {sourceRows.connected.length > 0 && (
            <button
              type="button"
              onClick={toggleExternalCollapsed}
              className="flex w-full items-center gap-1 px-2 pb-1 pt-2 text-left text-[11px] font-semibold uppercase tracking-wide text-muted hover:text-foreground"
            >
              <span
                aria-hidden
                className={`transition-transform ${externalCollapsed ? "-rotate-90" : ""}`}
              >
                ▾
              </span>
              External
            </button>
          )}
          {!externalCollapsed &&
            sourceRows.connected.map((row) => (
              <NavRow
                key={row.key}
                href={row.href}
                icon={row.icon}
                label={row.label}
                active={row.active}
              />
            ))}
          <button
            type="button"
            onClick={() => setAddSourceOpen(true)}
            className="page-row group/nav flex w-full min-w-0 items-center gap-1.5 rounded-md px-2 py-1 text-left text-[13px] text-dim transition-colors hover:bg-raised hover:text-foreground"
          >
            <span className="flex h-4 w-4 shrink-0 items-center justify-center text-[14px]" aria-hidden>
              ＋
            </span>
            <span className="min-w-0 flex-1 truncate">Add a new source</span>
          </button>
        </nav>
      ) : (
        <div className="mt-4 px-3 py-1.5 text-[12px] italic text-muted">
          No workspaces yet.
        </div>
      )}

      <div className="mt-6 border-t border-border px-2 py-2">
        {activeWorkspace ? (
          <NavRow
            href={`/workspaces/${activeWorkspace.id}/trash`}
            icon={<TrashIcon />}
            label="Trash"
            active={pathname === `/workspaces/${activeWorkspace.id}/trash`}
          />
        ) : null}
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
    {addSourceOpen && activeWorkspace && (
      <AddSourceModal
        workspaceId={activeWorkspace.id}
        returnTo={pathname}
        onClose={() => setAddSourceOpen(false)}
      />
    )}
    </>
  );
}
