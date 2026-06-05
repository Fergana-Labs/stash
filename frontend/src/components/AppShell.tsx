"use client";

import {
  ReactNode,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  getSessionDetail,
  publishCartridge,
  type SessionDetail,
  type CartridgeItemSpec,
} from "../lib/api";
import { track } from "../lib/analytics";
import { User, Workspace } from "../lib/types";
import AppSidebar from "./AppSidebar";
import CommandPalette from "./CommandPalette";
import CartridgeInviteCenter from "./CartridgeInviteCenter";
import { useShareModal } from "../lib/shareModalContext";
import { type Crumb, useBreadcrumbsValue } from "./BreadcrumbContext";
import { useShellChromeValue } from "./ShellChromeContext";
import {
  getCachedWorkspaces,
  readCachedWorkspaces,
} from "../lib/stashNavigationCache";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { recordRecent } from "../lib/pins";

interface AppShellProps {
  user: User;
  onLogout: () => void;
  children: ReactNode;
}

const SIDEBAR_KEY = "stash_sidebar_collapsed";
const SIDEBAR_WIDTH_KEY = "stash_sidebar_width";
const SIDEBAR_DEFAULT_WIDTH = 300;
const SIDEBAR_MIN_WIDTH = 220;
const SIDEBAR_MAX_WIDTH = 520;
const SIDEBAR_KEYBOARD_STEP = 16;

export interface SearchScope {
  kind:
    | "workspace"
    | "page"
    | "folder"
    | "session"
    | "stash"
    | "sessions"
    | "cartridges";
  label: string;
  detail: string;
  params: Record<string, string>;
}

type DirectShareTarget =
  | { kind: "page"; workspaceId: string; pageId: string; title: string }
  | { kind: "session"; workspaceId: string; sessionId: string };

type ShareStatus = "idle" | "creating" | "copied" | "error";

function readBool(key: string): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(key) === "1";
}

function clampSidebarWidth(width: number): number {
  return Math.min(
    SIDEBAR_MAX_WIDTH,
    Math.max(SIDEBAR_MIN_WIDTH, Math.round(width)),
  );
}

function readSidebarWidth(): number {
  if (typeof window === "undefined") return SIDEBAR_DEFAULT_WIDTH;
  const stored = localStorage.getItem(SIDEBAR_WIDTH_KEY);
  if (!stored) return SIDEBAR_DEFAULT_WIDTH;
  const width = Number(stored);
  if (!Number.isFinite(width)) return SIDEBAR_DEFAULT_WIDTH;
  return clampSidebarWidth(width);
}

// Pre-select the current page/folder/file/session when the Share button is
// clicked from a detail route, so "share this" is one click instead of a hunt
// through the picker.
function inferShareInitial(pathname: string): CartridgeItemSpec[] | undefined {
  const pageMatch = pathname.match(/^\/workspaces\/[^/]+\/p\/([^/?#]+)/);
  if (pageMatch)
    return [{ object_type: "page", object_id: pageMatch[1], position: 0 }];
  const folderMatch = pathname.match(
    /^\/workspaces\/[^/]+\/folders\/([^/?#]+)/,
  );
  if (folderMatch)
    return [{ object_type: "folder", object_id: folderMatch[1], position: 0 }];
  const fileMatch = pathname.match(/^\/workspaces\/[^/]+\/f\/([^/?#]+)/);
  if (fileMatch)
    return [{ object_type: "file", object_id: fileMatch[1], position: 0 }];
  const sessionMatch = pathname.match(
    /^\/workspaces\/[^/]+\/sessions\/([^/?#]+)/,
  );
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
    <svg
      className="h-4 w-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
      {collapsed && (
        <path d="M14 9l3 3-3 3" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

function SidebarResizeHandle({
  width,
  onPointerDown,
  onKeyDown,
}: {
  width: number;
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      role="separator"
      aria-label="Resize sidebar"
      aria-orientation="vertical"
      aria-valuemin={SIDEBAR_MIN_WIDTH}
      aria-valuemax={SIDEBAR_MAX_WIDTH}
      aria-valuenow={width}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      className="group absolute inset-y-0 right-0 z-20 w-2 translate-x-1/2 cursor-col-resize touch-none outline-none"
    >
      <div className="mx-auto h-full w-px bg-border transition-colors group-hover:bg-[var(--color-brand-300)] group-focus-visible:bg-[var(--color-brand-400)]" />
    </div>
  );
}

function lastCrumbLabel(crumbs: Crumb[] | null): string | null {
  const label = crumbs?.[crumbs.length - 1]?.label.trim();
  return label || null;
}

function inferDirectShareTarget(
  pathname: string,
  breadcrumbs: Crumb[] | null,
): DirectShareTarget | null {
  const pageMatch = pathname.match(/^\/workspaces\/([^/]+)\/p\/([^/?#]+)/);
  if (pageMatch) {
    return {
      kind: "page",
      workspaceId: pageMatch[1],
      pageId: pageMatch[2],
      title: lastCrumbLabel(breadcrumbs) ?? "Shared page",
    };
  }

  const sessionMatch = pathname.match(
    /^\/workspaces\/([^/]+)\/sessions\/([^/?#]+)/,
  );
  if (sessionMatch) {
    return {
      kind: "session",
      workspaceId: sessionMatch[1],
      sessionId: decodeURIComponent(sessionMatch[2]),
    };
  }

  return null;
}

function inferSearchScope(
  pathname: string,
  activeWorkspace: Workspace | undefined,
  breadcrumbs: Crumb[] | null,
): SearchScope | null {
  const stashMatch = pathname.match(/^\/cartridges\/([^/?#]+)/);
  if (stashMatch) {
    const slug = decodeURIComponent(stashMatch[1]);
    return {
      kind: "stash",
      label: "this cartridge",
      detail: "Search only in this cartridge",
      params: { stash: slug },
    };
  }

  const sessionMatch = pathname.match(
    /^\/workspaces\/([^/]+)\/sessions\/([^/?#]+)/,
  );
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

  const folderMatch = pathname.match(
    /^\/workspaces\/([^/]+)\/folders\/([^/?#]+)/,
  );
  if (folderMatch) {
    return {
      kind: "folder",
      label: lastCrumbLabel(breadcrumbs) ?? "this folder",
      detail: "Search only in this folder",
      params: { workspace: folderMatch[1], folder: folderMatch[2] },
    };
  }

  const sessionsMatch = pathname.match(
    /^\/workspaces\/([^/]+)\/sessions(?:\/)?$/,
  );
  if (sessionsMatch) {
    return {
      kind: "sessions",
      label: "sessions",
      detail: "Search sessions in this workspace",
      params: { workspace: sessionsMatch[1], content: "sessions" },
    };
  }

  const stashesMatch = pathname.match(
    /^\/workspaces\/([^/]+)\/cartridges(?:\/)?$/,
  );
  if (stashesMatch) {
    return {
      kind: "cartridges",
      label: "Cartridges",
      detail: "Search Cartridges in this workspace",
      params: { workspace: stashesMatch[1], content: "cartridges" },
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
      className="flex h-10 w-full items-center gap-2.5 rounded-full border border-border bg-surface px-4 text-left text-[14px] text-muted shadow-sm transition-colors hover:border-[var(--color-brand-300)] hover:bg-raised hover:text-foreground"
      aria-label="Search"
    >
      <svg
        className="h-4 w-4 shrink-0"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.3-4.3" />
      </svg>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="rounded bg-base px-1.5 py-0.5 font-mono text-[11px] text-muted ring-1 ring-border">
        ⌘K
      </span>
    </button>
  );
}

export default function AppShell({
  user,
  onLogout,
  children,
}: AppShellProps) {
  const pathname = usePathname();
  const breadcrumbs = useBreadcrumbsValue();
  const { shareAction, activeWorkspaceId: preferredWorkspaceId } =
    useShellChromeValue();
  const shareModal = useShareModal();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(
    preferredWorkspaceId,
  );
  const [workspaces, setWorkspaces] = useState<Workspace[]>(
    () => readCachedWorkspaces(user.id)?.all ?? [],
  );
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const [shareStatus, setShareStatus] = useState<ShareStatus>("idle");
  const [shareMessage, setShareMessage] = useState("");

  useEffect(() => {
    setSidebarCollapsed(readBool(SIDEBAR_KEY));
    setSidebarWidth(readSidebarWidth());
    getCachedWorkspaces(user.id)
      .then((r) => setWorkspaces(r.all))
      .catch(() => {});
  }, [user.id]);

  useEffect(() => {
    if (preferredWorkspaceId) setActiveWorkspaceId(preferredWorkspaceId);
  }, [preferredWorkspaceId]);

  useEffect(() => {
    const m = pathname.match(/^\/workspaces\/([^/]+)/);
    if (m?.[1]) setActiveWorkspaceId(m[1]);
  }, [pathname]);

  // Record per-user "recently viewed" whenever a page/file/folder opens, so
  // the Files Recent strip reflects this user's activity (not global mtime).
  useEffect(() => {
    const m = pathname.match(/^\/workspaces\/([^/]+)\/(p|f|folders)\/([^/?#]+)/);
    if (!m) return;
    const kind = m[2] === "p" ? "page" : m[2] === "f" ? "file" : "folder";
    recordRecent(m[1], decodeURIComponent(m[3]), kind);
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
          if (typeof window !== "undefined")
            localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
          return next;
        });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const activeWorkspace = workspaces.find((s) => s.id === activeWorkspaceId);
  const searchScope = inferSearchScope(pathname, activeWorkspace, breadcrumbs);
  const initial = user.display_name[0].toUpperCase();
  const accountLabel = user.email ?? user.name;
  const directShareTarget = inferDirectShareTarget(pathname, breadcrumbs);
  const shareInitial = inferShareInitial(pathname);

  function applySidebarWidth(width: number) {
    const next = clampSidebarWidth(width);
    setSidebarWidth(next);
    if (typeof window !== "undefined") {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(next));
    }
  }

  function startSidebarResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault();

    const startX = event.clientX;
    const startWidth = sidebarWidth;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function onPointerMove(moveEvent: PointerEvent) {
      applySidebarWidth(startWidth + moveEvent.clientX - startX);
    }

    function stopResize() {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }

  function resizeSidebarWithKeyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      applySidebarWidth(sidebarWidth - SIDEBAR_KEYBOARD_STEP);
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      applySidebarWidth(sidebarWidth + SIDEBAR_KEYBOARD_STEP);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      applySidebarWidth(SIDEBAR_MIN_WIDTH);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      applySidebarWidth(SIDEBAR_MAX_WIDTH);
    }
  }

  async function copyCurrentViewLink() {
    if (!activeWorkspaceId) return;

    const target = directShareTarget;
    if (!target) {
      shareModal.open({
        workspaceId: activeWorkspaceId,
        workspaceName: activeWorkspace?.name,
        initial: shareInitial,
      });
      return;
    }

    setShareStatus("creating");
    setShareMessage("");
    try {
      const result =
        target.kind === "page"
          ? await publishCartridge(
              target.workspaceId,
              target.title,
              [
                {
                  object_type: "page",
                  object_id: target.pageId,
                  position: 0,
                  label_override: target.title,
                },
              ],
              { discoverable: false },
            )
          : await publishSessionCartridge(target);
      track("web.session_shared", {
        workspace_id: target.workspaceId,
        cartridge_id: result.cartridge_id,
      });
      await navigator.clipboard.writeText(result.url);
      setShareStatus("copied");
      setShareMessage("Link copied");
      window.setTimeout(() => {
        setShareStatus("idle");
        setShareMessage("");
      }, 1600);
    } catch (e) {
      setShareStatus("error");
      setShareMessage(e instanceof Error ? e.message : "Share failed");
      window.setTimeout(() => {
        setShareStatus("idle");
        setShareMessage("");
      }, 3000);
    }
  }

  const defaultShareAction =
    activeWorkspaceId && shareInitial ? (
      <div className="mr-1 flex items-center gap-2">
        {shareMessage && (
          <span
            className={
              "max-w-[180px] truncate text-[11.5px] " +
              (shareStatus === "error" ? "text-red-500" : "text-muted")
            }
          >
            {shareMessage}
          </span>
        )}
        <button
          className="rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
          onClick={() => void copyCurrentViewLink()}
          disabled={shareStatus === "creating"}
        >
          {shareStatus === "creating"
            ? "Creating..."
            : shareStatus === "copied"
              ? "Copied"
              : "Share"}
        </button>
      </div>
    ) : null;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-base">
      <header className="sticky top-0 z-30 flex h-14 flex-shrink-0 items-center gap-3 border-b border-border bg-base/85 px-4 backdrop-blur-md">
        <div className="flex min-w-0 max-w-[30%] shrink items-center gap-1.5 text-[13px]">
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
          <Breadcrumb
            activeWorkspace={activeWorkspace}
            pageCrumbs={breadcrumbs}
          />
        </div>

        <div className="flex min-w-0 flex-1 justify-center">
          {/* Match the command-palette modal width (max-w-4xl) so the bar and
              the popup it opens read as the same element. */}
          <div className="w-full max-w-4xl">
            <TopSearchButton
              scope={searchScope}
              workspace={activeWorkspace}
              onClick={() => setCmdkOpen(true)}
            />
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-1">
          <CartridgeInviteCenter />
          {shareAction ?? defaultShareAction}
          <UserMenu
            initial={initial}
            accountLabel={accountLabel}
            onLogout={onLogout}
          />
        </div>
      </header>

      <div
        className="grid min-h-0 flex-1 overflow-hidden"
        style={{
          gridTemplateColumns: sidebarCollapsed
            ? "minmax(0, 1fr)"
            : `${sidebarWidth}px minmax(0, 1fr)`,
        }}
      >
        {!sidebarCollapsed && (
          <div className="relative min-h-0">
            <AppSidebar
              user={user}
              onLogout={onLogout}
              activeWorkspaceId={activeWorkspaceId}
            />
            <SidebarResizeHandle
              width={sidebarWidth}
              onPointerDown={startSidebarResize}
              onKeyDown={resizeSidebarWithKeyboard}
            />
          </div>
        )}
        <main className="flex min-w-0 flex-col overflow-y-auto bg-base">
          {children}
        </main>
      </div>

      <CommandPalette
        open={cmdkOpen}
        onClose={() => setCmdkOpen(false)}
        workspaceId={activeWorkspaceId}
        workspaceName={activeWorkspace?.name}
        searchScope={searchScope}
      />
    </div>
  );
}

async function publishSessionCartridge(
  target: Extract<DirectShareTarget, { kind: "session" }>,
) {
  const session = await getSessionDetail(target.workspaceId, target.sessionId);
  const title = sessionShareTitle(session);
  return publishCartridge(
    target.workspaceId,
    title,
    [
      {
        object_type: "session",
        object_id: session.id,
        position: 0,
        label_override: title,
      },
    ],
    { discoverable: false },
  );
}

function sessionShareTitle(session: SessionDetail): string {
  const title = session.title?.trim();
  if (title) return title;
  return `#${session.session_id}`;
}

function UserMenu({
  initial,
  accountLabel,
  onLogout,
}: {
  initial: string;
  accountLabel: string;
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
        title={accountLabel}
        className="ml-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-[10px] font-semibold text-[var(--color-brand-700)] hover:ring-2 hover:ring-[var(--color-brand-200)]"
      >
        {initial}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-1.5 w-64 max-w-[calc(100vw-2rem)] overflow-hidden rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg"
        >
          <div className="border-b border-border px-3 py-1.5 text-[11px] text-muted">
            Signed in as <span className="break-all text-foreground">{accountLabel}</span>
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

function Breadcrumb({
  activeWorkspace,
  pageCrumbs,
}: {
  activeWorkspace: Workspace | undefined;
  pageCrumbs: { label: string; href?: string; onClick?: () => void }[] | null;
}) {
  const home = {
    label: "Home",
    href: activeWorkspace ? `/workspaces/${activeWorkspace.id}` : "/",
  };

  let items: { label: string; href?: string }[] = [home];
  if (pageCrumbs && pageCrumbs.length > 0) {
    items = [
      ...items,
      ...pageCrumbs.map((c) => ({ label: c.label, href: c.href })),
    ];
  }

  return (
    <span className="flex min-w-0 items-center gap-1.5 text-muted">
      {items.map((c, i) => {
        const last = i === items.length - 1;
        return (
          <span key={i} className="flex min-w-0 items-center gap-1">
            {i > 0 && <span className="text-muted/60">/</span>}
            {c.href && (!last || c.label === "Home") ? (
              <Link href={c.href} className="truncate hover:text-foreground">
                {c.label}
              </Link>
            ) : (
              <span className="truncate font-medium text-foreground">
                {c.label}
              </span>
            )}
          </span>
        );
      })}
    </span>
  );
}
