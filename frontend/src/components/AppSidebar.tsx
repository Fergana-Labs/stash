"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { listMyWorkspaces } from "../lib/api";
import type { User, Workspace } from "../lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/search", label: "Search", icon: "S" },
  { href: "/memory", label: "History", icon: "H" },
  { href: "/notebooks", label: "Wiki", icon: "W" },
  { href: "/tables", label: "Tables", icon: "T" },
];

function IconTile({ letter, active }: { letter: string; active?: boolean }) {
  return (
    <span
      className={
        "flex h-5 w-5 flex-shrink-0 items-center justify-center rounded font-mono text-[10px] font-bold " +
        (active ? "bg-brand text-white" : "bg-raised text-muted")
      }
    >
      {letter}
    </span>
  );
}

function NavLink({
  item,
  isActive,
  wsId,
}: {
  item: NavItem;
  isActive: boolean;
  wsId?: string | null;
}) {
  const href = wsId ? `${item.href}?ws=${wsId}` : item.href;
  return (
    <Link
      href={href}
      className={
        "flex items-center gap-3 rounded-md px-[10px] py-2 text-[13px] transition-colors " +
        (isActive
          ? "bg-brand-muted font-medium text-brand"
          : "text-dim hover:bg-raised hover:text-foreground")
      }
    >
      <IconTile letter={item.icon} active={isActive} />
      {item.label}
    </Link>
  );
}

const WS_STORAGE_KEY = "stash_selected_workspace";

interface AppSidebarProps {
  user?: User;
}

export default function AppSidebar({ user }: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWsId, setSelectedWsId] = useState<string | null>(null);
  const [showWsSwitcher, setShowWsSwitcher] = useState(false);

  useEffect(() => {
    listMyWorkspaces()
      .then((res) => {
        const ws = res?.workspaces ?? [];
        setWorkspaces(ws);
        const saved =
          typeof window !== "undefined" ? localStorage.getItem(WS_STORAGE_KEY) : null;
        if (saved && ws.some((w) => w.id === saved)) {
          setSelectedWsId(saved);
        } else if (ws.length > 0) {
          setSelectedWsId(ws[0].id);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const wsMatch = pathname.match(/^\/workspaces\/([^/]+)/);
    if (wsMatch?.[1]) {
      setSelectedWsId(wsMatch[1]);
      localStorage.setItem(WS_STORAGE_KEY, wsMatch[1]);
      return;
    }
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const wsParam = params.get("ws");
      if (wsParam) {
        setSelectedWsId(wsParam);
        localStorage.setItem(WS_STORAGE_KEY, wsParam);
      }
    }
  }, [pathname]);

  const selectWorkspace = (wsId: string) => {
    setSelectedWsId(wsId);
    localStorage.setItem(WS_STORAGE_KEY, wsId);
    setShowWsSwitcher(false);

    const wsMatch = pathname.match(/^\/workspaces\/([^/]+)(.*)$/);
    if (wsMatch) {
      router.push(`/workspaces/${wsId}${wsMatch[2] ?? ""}`);
      return;
    }
    const params = new URLSearchParams(
      typeof window !== "undefined" ? window.location.search : ""
    );
    params.set("ws", wsId);
    router.push(`${pathname}?${params.toString()}`);
  };

  const selectedWs = workspaces.find((w) => w.id === selectedWsId);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  const displayName = user?.display_name || user?.name;
  const handle = user?.display_name ? user?.name : null;
  const avatarInitial = (displayName || "?")[0].toUpperCase();

  return (
    <aside className="flex w-[220px] flex-shrink-0 flex-col border-r border-border bg-surface">
      {/* Wordmark */}
      <div className="px-4 pb-2 pt-4">
        <Link
          href="/"
          className="font-display text-[20px] font-black tracking-[-0.03em] text-foreground"
        >
          stash
        </Link>
      </div>

      {/* Workspace switcher */}
      <div className="relative px-2 pb-2">
        <div className="flex w-full items-center gap-1 text-sm">
          <button
            onClick={() =>
              selectedWsId && router.push(`/workspaces/${selectedWsId}`)
            }
            className={
              "flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md border-0 px-[10px] py-2 text-[13px] font-medium transition-colors " +
              (selectedWs
                ? "bg-raised text-foreground hover:text-brand"
                : "text-dim hover:bg-raised hover:text-foreground")
            }
          >
            <IconTile letter="W" />
            <span className="flex-1 truncate text-left">
              {selectedWs?.name || "Select workspace"}
            </span>
          </button>
          <button
            onClick={() => setShowWsSwitcher((o) => !o)}
            className="flex h-8 w-8 flex-shrink-0 cursor-pointer items-center justify-center rounded-md border border-border bg-base text-muted transition-colors hover:border-foreground hover:bg-raised hover:text-foreground"
            aria-label="Switch workspace"
            aria-expanded={showWsSwitcher}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              className={
                "transition-transform " + (showWsSwitcher ? "rotate-180" : "")
              }
            >
              <path
                d="M3 4.5 L6 7.5 L9 4.5"
                stroke="currentColor"
                strokeWidth="1.5"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>

        {showWsSwitcher && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setShowWsSwitcher(false)}
            />
            <div className="absolute left-2 right-2 top-full z-50 mt-1 rounded-lg border border-border bg-surface py-1 shadow-[0_12px_30px_rgba(15,23,42,0.08),0_2px_4px_rgba(15,23,42,0.04)]">
              {workspaces.map((ws) => (
                <button
                  key={ws.id}
                  onClick={() => selectWorkspace(ws.id)}
                  className="block w-full cursor-pointer px-3 py-2 text-left text-[13px] transition-colors hover:bg-raised"
                >
                  <div
                    className={
                      "truncate font-medium " +
                      (ws.id === selectedWsId ? "text-brand" : "text-foreground")
                    }
                  >
                    {ws.name}
                  </div>
                  {ws.description && (
                    <div className="mt-[1px] truncate text-[10px] text-muted">
                      {ws.description}
                    </div>
                  )}
                </button>
              ))}
              {workspaces.length === 0 && (
                <div className="px-3 py-2 text-xs text-muted">No workspaces yet</div>
              )}
              <div className="mt-1 border-t border-border-subtle pt-1">
                <Link
                  href="/rooms"
                  onClick={() => setShowWsSwitcher(false)}
                  className="block px-3 py-1.5 text-[11px] text-muted transition-colors hover:text-foreground"
                >
                  Manage workspaces…
                </Link>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            isActive={isActive(item.href)}
            wsId={selectedWsId}
          />
        ))}
      </nav>

      {/* Docs */}
      <div className="px-2 pb-2">
        <Link
          href="/docs"
          className={
            "flex items-center gap-3 rounded-md px-[10px] py-2 text-[13px] transition-colors " +
            (isActive("/docs")
              ? "bg-brand-muted font-medium text-brand"
              : "text-dim hover:bg-raised hover:text-foreground")
          }
        >
          <IconTile letter="?" active={isActive("/docs")} />
          Docs
        </Link>
      </div>

      {/* User block */}
      {user && (
        <div className="border-t border-border-subtle px-2 py-3">
          <Link
            href="/settings"
            className="flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-raised"
          >
            <span
              className="inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full font-display text-[10px] font-bold text-white"
              style={{ background: "var(--color-human)" }}
            >
              {avatarInitial}
            </span>
            <div className="flex min-w-0 flex-col">
              <div className="truncate text-[12px] font-medium text-foreground">
                {displayName}
              </div>
              {handle && (
                <div className="truncate text-[10px] text-muted">@{handle}</div>
              )}
            </div>
          </Link>
        </div>
      )}
    </aside>
  );
}
