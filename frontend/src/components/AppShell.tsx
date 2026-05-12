"use client";

import { ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { User, Workspace } from "../lib/types";
import AppSidebar from "./AppSidebar";
import CommandPalette from "./CommandPalette";
import ShareModal from "./ShareModal";
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeStashId, setActiveStashId] = useState<string | null>(null);
  const [stashes, setStashes] = useState<Workspace[]>(
    () => readCachedWorkspaces(user.id)?.all ?? []
  );
  const [shareOpen, setShareOpen] = useState(false);
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
          <Link
            href="/settings"
            className="ml-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-[10px] font-semibold text-[var(--color-brand-700)]"
            title={user.display_name || user.name}
          >
            {initial}
          </Link>
          {activeStashId && (
            <button
              className="ml-1 rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
              onClick={() => setShareOpen(true)}
            >
              Share
            </button>
          )}
          <button onClick={onLogout} className="rounded p-1 text-muted hover:bg-raised" title="Sign out">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
              <circle cx="5" cy="12" r="1.5" />
              <circle cx="12" cy="12" r="1.5" />
              <circle cx="19" cy="12" r="1.5" />
            </svg>
          </button>
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

      {activeStashId && (
        <ShareModal
          open={shareOpen}
          stashId={activeStashId}
          stashName={activeStash?.name || "Stash"}
          onClose={() => setShareOpen(false)}
        />
      )}
      <CommandPalette
        open={cmdkOpen}
        onClose={() => setCmdkOpen(false)}
        stashId={activeStashId}
      />
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
