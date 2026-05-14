"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ViewItemSpec } from "../lib/api";
import { User, Workspace } from "../lib/types";
import AppSidebar from "./AppSidebar";
import CommandPalette from "./CommandPalette";
import { useShareModal } from "../lib/shareModalContext";
import { useBreadcrumbsValue } from "./BreadcrumbContext";
import { StashIcon } from "./StashIcons";
import { getCachedWorkspaces, readCachedWorkspaces } from "../lib/stashNavigationCache";

interface AppShellProps {
  user: User;
  onLogout: () => void;
  children: ReactNode;
}

const SIDEBAR_KEY = "stash_sidebar_collapsed";

function readBool(key: string): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(key) === "1";
}

// Pre-select the current page/folder/file/session when the Share button is
// clicked from a detail route, so "share this" is one click instead of a hunt
// through the picker.
function inferShareInitial(pathname: string): ViewItemSpec[] | undefined {
  const pageMatch = pathname.match(/^\/stashes\/[^/]+\/p\/([^/?#]+)/);
  if (pageMatch) return [{ object_type: "page", object_id: pageMatch[1], position: 0 }];
  const folderMatch = pathname.match(/^\/stashes\/[^/]+\/folders\/([^/?#]+)/);
  if (folderMatch) return [{ object_type: "folder", object_id: folderMatch[1], position: 0 }];
  const fileMatch = pathname.match(/^\/stashes\/[^/]+\/f\/([^/?#]+)/);
  if (fileMatch) return [{ object_type: "file", object_id: fileMatch[1], position: 0 }];
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

export default function AppShell({ user, onLogout, children }: AppShellProps) {
  const pathname = usePathname();
  const breadcrumbs = useBreadcrumbsValue();
  const shareModal = useShareModal();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeStashId, setActiveStashId] = useState<string | null>(null);
  const [stashes, setStashes] = useState<Workspace[]>(
    () => readCachedWorkspaces(user.id)?.all ?? []
  );
  const [cmdkOpen, setCmdkOpen] = useState(false);

  useEffect(() => {
    setSidebarCollapsed(readBool(SIDEBAR_KEY));
    getCachedWorkspaces(user.id)
      .then((r) => setStashes(r.all))
      .catch(() => {});
  }, [user.id]);

  useEffect(() => {
    const m =
      pathname.match(/^\/stashes\/([^/]+)/) ||
      pathname.match(/^\/workspaces\/([^/]+)/);
    if (m?.[1]) setActiveStashId(m[1]);
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

  const activeStash = stashes.find((s) => s.id === activeStashId);
  const initial = (user.display_name || user.name || "?")[0].toUpperCase();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-base">
      <header className="sticky top-0 z-30 flex h-11 flex-shrink-0 items-center justify-between border-b border-border bg-base/85 px-3 backdrop-blur-md">
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
          <Breadcrumb activeStash={activeStash} pageCrumbs={breadcrumbs} />
        </div>

        <div className="flex items-center gap-1">
          {activeStashId && (
            <button
              className="mr-1 rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
              onClick={() =>
                shareModal.open({
                  stashId: activeStashId,
                  stashName: activeStash?.name,
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
            cmdkOpen={cmdkOpen}
            onCmdkOpen={() => setCmdkOpen(true)}
          />
        )}
        <main className="flex min-w-0 flex-col overflow-y-auto bg-base">
          {children}
        </main>
      </div>

      <CommandPalette
        open={cmdkOpen}
        onClose={() => setCmdkOpen(false)}
        stashId={activeStashId}
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

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
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
            Settings
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
  activeStash,
  pageCrumbs,
}: {
  activeStash: Workspace | undefined;
  pageCrumbs: { label: string; href?: string; onClick?: () => void }[] | null;
}) {
  const items: { label: string; href?: string }[] = [];
  if (activeStash) {
    items.push({ label: activeStash.name, href: `/stashes/${activeStash.id}` });
  } else {
    items.push({ label: "Stashes", href: "/" });
  }
  if (pageCrumbs && pageCrumbs.length > 0) {
    pageCrumbs.forEach((c) => items.push({ label: c.label, href: c.href }));
  }

  return (
    <span className="ml-1.5 flex min-w-0 items-center gap-1.5 text-muted">
      {items.map((c, i) => {
        const last = i === items.length - 1;
        const isStash = i === 0;
        return (
          <span key={i} className="flex min-w-0 items-center gap-1">
            {i > 0 && <span className="text-muted/60">/</span>}
            {isStash && (
              <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
                <StashIcon />
              </span>
            )}
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
