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
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { User } from "../lib/types";
import AppSidebar from "./AppSidebar";
import CommandPalette from "./CommandPalette";
import { type Crumb, useBreadcrumbsValue } from "./BreadcrumbContext";
import { useShellChromeValue } from "./ShellChromeContext";
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
  kind: "page" | "folder" | "session" | "skill" | "sessions" | "skills" | "all";
  label: string;
  detail: string;
  params: Record<string, string>;
}

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

function inferSearchScope(
  pathname: string,
  breadcrumbs: Crumb[] | null,
): SearchScope | null {
  const skillMatch = pathname.match(/^\/skills\/([^/?#]+)/);
  if (skillMatch) {
    const slug = decodeURIComponent(skillMatch[1]);
    return {
      kind: "skill",
      label: "this skill",
      detail: "Search only in this skill",
      params: { skill: slug },
    };
  }

  const sessionMatch = pathname.match(/^\/sessions\/([^/?#]+)/);
  if (sessionMatch) {
    const sessionId = decodeURIComponent(sessionMatch[1]);
    return {
      kind: "session",
      label: "this session",
      detail: `Search only in #${sessionId}`,
      params: { session: sessionId },
    };
  }

  const pageMatch = pathname.match(/^\/p\/([^/?#]+)/);
  if (pageMatch) {
    return {
      kind: "page",
      label: lastCrumbLabel(breadcrumbs) ?? "this page",
      detail: "Search only in this page",
      params: { page: pageMatch[1] },
    };
  }

  const folderMatch = pathname.match(/^\/folders\/([^/?#]+)/);
  if (folderMatch) {
    return {
      kind: "folder",
      label: lastCrumbLabel(breadcrumbs) ?? "this folder",
      detail: "Search only in this folder",
      params: { folder: folderMatch[1] },
    };
  }

  const sessionsMatch = pathname.match(/^\/sessions(?:\/)?$/);
  if (sessionsMatch) {
    return {
      kind: "sessions",
      label: "sessions",
      detail: "Search your sessions",
      params: { content: "sessions" },
    };
  }

  const skillsMatch = pathname.match(/^\/skills(?:\/)?$/);
  if (skillsMatch) {
    return {
      kind: "skills",
      label: "Skills",
      detail: "Search your Skills",
      params: { content: "skills" },
    };
  }

  if (pathname === "/" || pathname === "/files") {
    return {
      kind: "all",
      label: "Stash",
      detail: "Search everything",
      params: {},
    };
  }

  return null;
}

function TopSearchButton({
  scope,
  onClick,
}: {
  scope: SearchScope | null;
  onClick: () => void;
}) {
  const label = scope ? `Search ${scope.label}` : "Search";

  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-full border border-border bg-surface px-4 text-left text-[14px] text-muted shadow-sm transition-colors hover:border-[var(--color-brand-300)] hover:bg-raised hover:text-foreground"
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

// On the /search route the top bar is a live text input that drives the
// results in real time (it writes the query into the URL, which the search
// page reads). The command palette stays reachable via the ⌘K affordance and
// the global ⌘K shortcut.
function InlineSearchInput({
  onOpenPalette,
}: {
  onOpenPalette: () => void;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [value, setValue] = useState(searchParams.get("q") ?? "");

  // Keep the field in sync when `q` changes from elsewhere (e.g. running a
  // scoped search from the command palette).
  useEffect(() => {
    setValue(searchParams.get("q") ?? "");
  }, [searchParams]);

  // Debounced write of the query into the URL; the search page reads `q` and
  // re-runs its search as this changes.
  useEffect(() => {
    const current = searchParams.get("q") ?? "";
    if (value === current) return;
    const handle = window.setTimeout(() => {
      const params = new URLSearchParams(Array.from(searchParams.entries()));
      if (value) params.set("q", value);
      else params.delete("q");
      router.replace(`/search?${params.toString()}`, { scroll: false });
    }, 180);
    return () => window.clearTimeout(handle);
  }, [value, router, searchParams]);

  return (
    <div className="flex h-10 w-full items-center gap-2.5 rounded-full border border-border bg-surface px-4 text-[14px] shadow-sm transition-colors focus-within:border-[var(--color-brand-300)]">
      <svg
        className="h-4 w-4 shrink-0 text-muted"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.3-4.3" />
      </svg>
      <input
        type="text"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Search pages, sessions, tables, and Skills…"
        aria-label="Search"
        autoFocus
        className="min-w-0 flex-1 bg-transparent text-foreground placeholder:text-muted outline-none"
      />
      <button
        type="button"
        onClick={onOpenPalette}
        aria-label="Open command palette"
        title="Command palette (⌘K)"
        className="shrink-0 cursor-pointer rounded bg-base px-1.5 py-0.5 font-mono text-[11px] text-muted ring-1 ring-border transition-colors hover:text-foreground"
      >
        ⌘K
      </button>
    </div>
  );
}

export default function AppShell({
  user,
  onLogout,
  children,
}: AppShellProps) {
  const pathname = usePathname();
  const breadcrumbs = useBreadcrumbsValue();
  const { shareAction } = useShellChromeValue();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const searchBarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSidebarCollapsed(readBool(SIDEBAR_KEY));
    setSidebarWidth(readSidebarWidth());
  }, []);

  // Record "recently viewed" whenever a folder opens, so the Files Recent
  // strip reflects this user's activity (not global mtime). Pages and files
  // record from their own clients once the loaded resource is known.
  useEffect(() => {
    const m = pathname.match(/^\/folders\/([^/?#]+)/);
    if (!m) return;
    recordRecent(decodeURIComponent(m[1]), "folder");
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

  const searchScope = inferSearchScope(pathname, breadcrumbs);
  const isSearchPage = pathname === "/search";

  // Browser tab title: the most specific thing we know — the current item or
  // section from breadcrumbs, falling back to the user's name on home —
  // suffixed with the brand. Item viewers (pages, sessions, files) set the last
  // crumb to their own name, so this covers them too.
  const documentTitle = lastCrumbLabel(breadcrumbs) ?? user.display_name;
  useEffect(() => {
    document.title = documentTitle ? `${documentTitle} - Stash` : "Stash";
  }, [documentTitle]);
  const initial = user.display_name[0].toUpperCase();
  const accountLabel = user.email ?? user.name;
  const usernameLabel = `@${user.name}`;

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
            className="cursor-pointer rounded p-1 text-muted hover:bg-raised"
            aria-label="Toggle sidebar"
            title="Toggle sidebar (⌘\\)"
          >
            <SidebarToggleIcon collapsed={sidebarCollapsed} />
          </button>
          <Breadcrumb pageCrumbs={breadcrumbs} />
        </div>

        <div className="flex min-w-0 flex-1 justify-center">
          {/* The popup measures this element on open so it lines up exactly
              with the bar, regardless of sidebar/breadcrumb width. */}
          <div ref={searchBarRef} className="w-full max-w-4xl">
            {isSearchPage ? (
              <InlineSearchInput onOpenPalette={() => setCmdkOpen(true)} />
            ) : (
              <TopSearchButton
                scope={searchScope}
                onClick={() => setCmdkOpen(true)}
              />
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-1">
          {shareAction}
          <UserMenu
            initial={initial}
            accountLabel={accountLabel}
            usernameLabel={usernameLabel}
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
            <AppSidebar user={user} onLogout={onLogout} />
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
        anchorRef={searchBarRef}
        searchScope={searchScope}
      />
    </div>
  );
}

function UserMenu({
  initial,
  accountLabel,
  usernameLabel,
  onLogout,
}: {
  initial: string;
  accountLabel: string;
  usernameLabel: string;
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
        className="ml-1 inline-flex h-6 w-6 cursor-pointer items-center justify-center rounded-full bg-brand-100 text-[10px] font-semibold text-[var(--color-brand-700)] hover:ring-2 hover:ring-[var(--color-brand-200)]"
      >
        {initial}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-1.5 w-64 max-w-[calc(100vw-2rem)] overflow-hidden rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg"
        >
          <div className="border-b border-border px-3 py-1.5 text-[11px] text-muted">
            <div>
              Signed in as <span className="break-all text-foreground">{accountLabel}</span>
            </div>
            <div className="mt-0.5">
              Username <span className="break-all text-foreground">{usernameLabel}</span>
            </div>
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
            className="block w-full cursor-pointer px-3 py-1.5 text-left text-foreground hover:bg-raised"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Breadcrumb({
  pageCrumbs,
}: {
  pageCrumbs: { label: string; href?: string; onClick?: () => void }[] | null;
}) {
  const home = { label: "Home", href: "/" };

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
