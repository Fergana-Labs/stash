"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import type { User, Workspace } from "../lib/types";
import { listMyWorkspaces } from "../lib/api";

interface TopBarProps {
  user: User;
  onLogout: () => void;
}

const WS_STORAGE_KEY = "stash_selected_workspace";

const SEGMENT_LABELS: Record<string, string> = {
  memory: "History",
  notebooks: "Wiki",
  search: "Search",
  files: "Files",
  rooms: "Workspaces",
  tables: "Tables",
  settings: "Settings",
  docs: "Docs",
  workspaces: "Workspaces",
};

function titleCase(seg: string) {
  return seg.charAt(0).toUpperCase() + seg.slice(1);
}

export default function TopBar({ user, onLogout }: TopBarProps) {
  const pathname = usePathname();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWsId, setSelectedWsId] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listMyWorkspaces()
      .then((res) => setWorkspaces(res?.workspaces ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const wsMatch = pathname.match(/^\/workspaces\/([^/]+)/);
    if (wsMatch?.[1]) {
      setSelectedWsId(wsMatch[1]);
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const wsParam = params.get("ws");
    if (wsParam) {
      setSelectedWsId(wsParam);
      return;
    }
    const saved = localStorage.getItem(WS_STORAGE_KEY);
    if (saved) setSelectedWsId(saved);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [menuOpen]);

  const crumbs = useMemo(() => {
    const selected = workspaces.find((w) => w.id === selectedWsId);
    const wsLabel = selected?.name ?? "stash";

    const segs = pathname.split("/").filter(Boolean);

    if (segs.length === 0) return [wsLabel];

    if (segs[0] === "docs") return ["stash", "Docs", ...segs.slice(1).map(titleCase)];

    if (segs[0] === "workspaces" && segs[1]) {
      const rest = segs.slice(2).map((s) => SEGMENT_LABELS[s] ?? titleCase(s));
      return [wsLabel, ...rest];
    }

    const mapped = segs.map((s) => SEGMENT_LABELS[s] ?? titleCase(s));
    return [wsLabel, ...mapped];
  }, [pathname, selectedWsId, workspaces]);

  const displayName = user.display_name || user.name;
  const handle = user.display_name ? user.name : null;
  const initial = (displayName || "?")[0].toUpperCase();

  return (
    <div className="sticky top-0 z-10 flex h-12 items-center justify-between border-b border-border bg-base px-6">
      <nav className="flex items-center gap-2 text-[12px] text-muted">
        {crumbs.map((c, i) => (
          <span key={i} className="flex items-center gap-2">
            {i > 0 && <span className="text-muted">/</span>}
            <span
              className={
                i === crumbs.length - 1
                  ? "font-medium text-foreground"
                  : "text-muted"
              }
            >
              {c}
            </span>
          </span>
        ))}
      </nav>
      <div className="flex items-center gap-3">
        <span className="hidden font-mono text-[10px] uppercase tracking-[0.08em] text-muted sm:inline">
          ⌘K to search
        </span>
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            className="inline-flex h-[26px] w-[26px] items-center justify-center rounded-full font-display text-[11px] font-bold text-white"
            style={{ background: "var(--color-human)" }}
            aria-label="Account menu"
          >
            {initial}
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-[34px] z-50 w-56 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-[0_12px_30px_rgba(15,23,42,0.08),0_2px_4px_rgba(15,23,42,0.04)]">
              <div className="border-b border-border-subtle px-3 py-2">
                <div className="truncate text-[13px] font-medium text-foreground">
                  {displayName}
                </div>
                {handle && (
                  <div className="truncate text-[10px] text-muted">@{handle}</div>
                )}
              </div>
              <Link
                href="/settings"
                onClick={() => setMenuOpen(false)}
                className="block px-3 py-2 text-[13px] text-foreground transition hover:bg-raised"
              >
                Settings
              </Link>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onLogout();
                }}
                className="block w-full px-3 py-2 text-left text-[13px] text-foreground transition hover:bg-raised"
              >
                Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
