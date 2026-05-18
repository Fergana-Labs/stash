"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { StashItemSpec } from "../lib/api";
import { User, Workspace } from "../lib/types";
import AppSidebar from "./AppSidebar";
import CommandPalette from "./CommandPalette";
import { useShareModal } from "../lib/shareModalContext";
import { type Crumb, useBreadcrumbsValue } from "./BreadcrumbContext";
import { StashIcon } from "./StashIcons";
import { getCachedWorkspaces, readCachedWorkspaces } from "../lib/stashNavigationCache";
import { useEscapeKey } from "../hooks/useEscapeKey";

interface AppShellProps {
  user: User;
  onLogout: () => void;
  children: ReactNode;
}

const SIDEBAR_KEY = "stash_sidebar_collapsed";

export interface SearchScope {
  kind: "workspace" | "page" | "folder" | "session" | "stash" | "sessions" | "stashes";
  label: string;
  detail: string;
  params: Record<string, string>;
}

function readBool(key: string): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(key) === "1";
}

// Pre-select the current page/folder/file/session when the Share button is
// clicked from a detail route, so "share this" is one click instead of a hunt
// through the picker.
function inferShareInitial(pathname: string): StashItemSpec[] | undefined {
  const pageMatch = pathname.match(/^\/workspaces\/[^/]+\/p\/([^/?#]+)/);
  if (pageMatch) return [{ object_type: "page", object_id: pageMatch[1], position: 0 }];
  const folderMatch = pathname.match(/^\/workspaces\/[^/]+\/folders\/([^/?#]+)/);
  if (folderMatch) return [{ object_type: "folder", object_id: folderMatch[1], position: 0 }];
  const fileMatch = pathname.match(/^\/workspaces\/[^/]+\/f\/([^/?#]+)/);
  if (fileMatch) return [{ object_type: "file", object_id: fileMatch[1], position: 0 }];
  const sessionMatch = pathname.match(/^\/workspaces\/[^/]+\/sessions\/([^/?#]+)/);
  if (sessionMatch) {
    const sessionId = decodeURIComponent(sessionMatch[1]);
    return [
      {
        object_type: "session",
        object_id: sessionId,
        position: 0,
        label_override: `#${sessionId}`,
      },
    ];
  }
  return undefined;
}

function SidebarToggleIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
      {collapsed && <path d="M14 9l3 3-3 3" strokeLinecap="round" strokeLinejoin="round" />}
    </svg>
  );
}

function lastCrumbLabel(crumbs: Crumb[] | null): string | null {
  const label = crumbs?.[crumbs.length - 1]?.label.trim();
  return label || null;
}

function inferSearchScope(
  pathname: string,
  activeWorkspace: Workspace | undefined,
  breadcrumbs: Crumb[] | null
): SearchScope | null {
  const stashMatch = pathname.match(/^\/stashes\/([^/?#]+)/);
  if (stashMatch) {
    const slug = decodeURIComponent(stashMatch[1]);
    return {
      kind: "stash",
      label: "this Stash",
      detail: "Search only in this Stash",
      params: { stash: slug },
    };
  }

  const sessionMatch = pathname.match(/^\/workspaces\/([^/]+)\/sessions\/([^/?#]+)/);
  if (sessionMatch) {
    const sessionId = decodeURIComponent(sessionMatch[2]);
    return {
      kind: "session",
      label: "this session",
      detail: `Search only in #${sessionId}`,
      params: { workspace: sessionMatch[1], session: sessionId },
    };
  }

  const pageMatch = pathname.match(/^\/workspaces\/([^/]+)\/p\/([^/?#]+)/);
  if (pageMatch) {
    return {
      kind: "page",
      label: lastCrumbLabel(breadcrumbs) ?? "this page",
      detail: "Search only in this page",
      params: { workspace: pageMatch[1], page: pageMatch[2] },
    };
  }

  const folderMatch = pathname.match(/^\/workspaces\/([^/]+)\/folders\/([^/?#]+)/);
  if (folderMatch) {
    return {
      kind: "folder",
      label: lastCrumbLabel(breadcrumbs) ?? "this folder",
      detail: "Search only in this folder",
      params: { workspace: folderMatch[1], folder: folderMatch[2] },
    };
  }

  const sessionsMatch = pathname.match(/^\/workspaces\/([^/]+)\/sessions(?:\/)?$/);
  if (sessionsMatch) {
    return {
      kind: "sessions",
      label: "sessions",
      detail: "Search sessions in this workspace",
      params: { workspace: sessionsMatch[1], content: "sessions" },
    };
  }

  const stashesMatch = pathname.match(/^\/workspaces\/([^/]+)\/stashes(?:\/)?$/);
  if (stashesMatch) {
    return {
      kind: "stashes",
      label: "Stashes",
      detail: "Search Stashes in this workspace",
      params: { workspace: stashesMatch[1], content: "stashes" },
    };
  }

  const workspaceMatch = pathname.match(/^\/workspaces\/([^/]+)(?:\/)?$/);
  if (workspaceMatch) {
    return {
      kind: "workspace",
      label: activeWorkspace?.name ?? "this workspace",
      detail: "Search this workspace",
      params: { workspace: workspaceMatch[1] },
    };
  }

  return null;
}

function TopSearchButton({
  scope,
  workspace,
  onClick,
}: {
  scope: SearchScope | null;
  workspace?: Workspace;
  onClick: () => void;
}) {
  const label = scope
    ? `Search ${scope.label}`
    : workspace
      ? `Search ${workspace.name}`
      : "Search";

  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-7 w-full items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-left text-[12.5px] text-muted shadow-sm hover:border-[var(--color-brand-300)] hover:bg-raised hover:text-foreground"
      aria-label="Search"
    >
      <svg
        className="h-3.5 w-3.5 shrink-0"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.3-4.3" />
      </svg>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="rounded bg-base px-1.5 py-0.5 font-mono text-[10px] text-muted ring-1 ring-border">
        ⌘K
      </span>
    </button>
  );
}

export default function AppShell({ user, onLogout, children }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const breadcrumbs = useBreadcrumbsValue();
  const shareModal = useShareModal();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>(
    () => readCachedWorkspaces(user.id)?.all ?? []
  );
  const [cmdkOpen, setCmdkOpen] = useState(false);

  useEffect(() => {
    setSidebarCollapsed(readBool(SIDEBAR_KEY));
    getCachedWorkspaces(user.id)
      .then((r) => setWorkspaces(r.all))
      .catch(() => {});
  }, [user.id]);

  useEffect(() => {
    const m = pathname.match(/^\/workspaces\/([^/]+)/);
    if (m?.[1]) setActiveWorkspaceId(m[1]);
  }, [pathname]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdkOpen((o) => !o);
      }
      if ((e.metaKey || e.ctrlKey) && e.key === "\\") {
        e.preventDefault();
        setSidebarCollapsed((c) => {
          const next = !c;
          if (typeof window !== "undefined") localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
          return next;
        });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const activeWorkspace = workspaces.find((s) => s.id === activeWorkspaceId);
  const searchScope = inferSearchScope(pathname, activeWorkspace, breadcrumbs);
  const initial = (user.display_name || user.name || "?")[0].toUpperCase();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-base">
      <header className="sticky top-0 z-30 grid h-11 flex-shrink-0 grid-cols-[minmax(0,1fr)_minmax(220px,460px)_minmax(0,1fr)] items-center gap-3 border-b border-border bg-base/85 px-3 backdrop-blur-md">
        <div className="flex min-w-0 items-center gap-1.5 text-[13px]">
          <button
            onClick={() => {
              setSidebarCollapsed((c) => {
                const next = !c;
                if (typeof window !== "undefined")
                  localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
                return next;
              });
            }}
            className="rounded p-1 text-muted hover:bg-raised"
            aria-label="Toggle sidebar"
            title="Toggle sidebar (⌘\\)"
          >
            <SidebarToggleIcon collapsed={sidebarCollapsed} />
          </button>
          <button
            onClick={() => router.back()}
            className="rounded p-1 text-muted hover:bg-raised"
            aria-label="Back"
            title="Back"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 18l-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <WorkspaceLabel workspace={activeWorkspace} />
          <Breadcrumb activeWorkspace={activeWorkspace} pageCrumbs={breadcrumbs} />
        </div>

        <TopSearchButton
          scope={searchScope}
          workspace={activeWorkspace}
          onClick={() => setCmdkOpen(true)}
        />

        <div className="flex items-center justify-end gap-1">
          {activeWorkspaceId && (
            <button
              className="mr-1 rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
              onClick={() =>
                shareModal.open({
                  workspaceId: activeWorkspaceId,
                  workspaceName: activeWorkspace?.name,
                  initial: inferShareInitial(pathname),
                })
              }
            >
              Share
            </button>
          )}
          <UserMenu
            initial={initial}
            label={user.display_name || user.name}
            onLogout={onLogout}
          />
        </div>
      </header>

      <div
        className="grid min-h-0 flex-1 overflow-hidden"
        style={{
          gridTemplateColumns: sidebarCollapsed ? "minmax(0, 1fr)" : "260px minmax(0, 1fr)",
        }}
      >
        {!sidebarCollapsed && (
          <AppSidebar
            user={user}
            onLogout={onLogout}
            activeWorkspaceId={activeWorkspaceId}
          />
        )}
        <main className="flex min-w-0 flex-col overflow-y-auto bg-base">
          {children}
        </main>
      </div>

      <CommandPalette
        open={cmdkOpen}
        onClose={() => setCmdkOpen(false)}
        workspaceId={activeWorkspaceId}
        searchScope={searchScope}
      />
    </div>
  );
}

function UserMenu({
  initial,
  label,
  onLogout,
}: {
  initial: string;
  label: string;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={label}
        className="ml-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-[10px] font-semibold text-[var(--color-brand-700)] hover:ring-2 hover:ring-[var(--color-brand-200)]"
      >
        {initial}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-1.5 w-44 overflow-hidden rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg"
        >
          <div className="border-b border-border px-3 py-1.5 text-[11px] text-muted">
            Signed in as <span className="text-foreground">{label}</span>
          </div>
          <Link
            href="/settings"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="block px-3 py-1.5 text-foreground hover:bg-raised"
          >
            Account settings
          </Link>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className="block w-full px-3 py-1.5 text-left text-foreground hover:bg-raised"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function WorkspaceLabel({ workspace }: { workspace: Workspace | undefined }) {
  if (!workspace) return null;

  return (
    <Link
      href={`/workspaces/${workspace.id}`}
      className="ml-1.5 flex min-w-0 items-center gap-1.5 rounded px-1.5 py-1 text-foreground hover:bg-raised"
      title={workspace.name}
    >
      <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
        <StashIcon />
      </span>
      <span className="max-w-[180px] truncate font-medium">{workspace.name}</span>
    </Link>
  );
}

function Breadcrumb({
  activeWorkspace,
  pageCrumbs,
}: {
  activeWorkspace: Workspace | undefined;
  pageCrumbs: { label: string; href?: string; onClick?: () => void }[] | null;
}) {
  let items: { label: string; href?: string }[] = [];
  if (pageCrumbs && pageCrumbs.length > 0) {
    items = pageCrumbs.map((c) => ({ label: c.label, href: c.href }));
  } else if (activeWorkspace) {
    items = [{ label: "Home", href: `/workspaces/${activeWorkspace.id}` }];
  } else {
    items = [{ label: "Home", href: "/" }];
  }

  return (
    <span className="flex min-w-0 items-center gap-1.5 text-muted">
      {items.map((c, i) => {
        const last = i === items.length - 1;
        return (
          <span key={i} className="flex min-w-0 items-center gap-1">
            <span className="text-muted/60">/</span>
            {!last && c.href ? (
              <Link href={c.href} className="truncate hover:text-foreground">
                {c.label}
              </Link>
            ) : (
              <span className="truncate font-medium text-foreground">{c.label}</span>
            )}
          </span>
        );
      })}
    </span>
  );
}
