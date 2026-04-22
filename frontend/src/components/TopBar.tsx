"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import type { User, Workspace } from "../lib/types";
import { listMyWorkspaces } from "../lib/api";
import { useBreadcrumbsValue, type Crumb } from "./BreadcrumbContext";

interface TopBarProps {
  user: User;
  onLogout: () => void;
}

const WS_STORAGE_KEY = "stash_selected_workspace";

const SEGMENT_LABELS: Record<string, { label: string; href: string }> = {
  memory: { label: "History", href: "/memory" },
  notebooks: { label: "Wiki", href: "/notebooks" },
  search: { label: "Search", href: "/search" },
  files: { label: "Files", href: "/files" },
  rooms: { label: "Workspaces", href: "/rooms" },
  tables: { label: "Tables", href: "/tables" },
  settings: { label: "Settings", href: "/settings" },
  docs: { label: "Docs", href: "/docs" },
  workspaces: { label: "Workspaces", href: "/rooms" },
};

function titleCase(seg: string) {
  return seg.charAt(0).toUpperCase() + seg.slice(1);
}

export default function TopBar({ user, onLogout }: TopBarProps) {
  const pathname = usePathname();
  const pageCrumbs = useBreadcrumbsValue();
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

  const crumbs: Crumb[] = useMemo(() => {
    const selected = workspaces.find((w) => w.id === selectedWsId);
    const wsName = selected?.name ?? "stash";
    const wsHref = selectedWsId ? `/workspaces/${selectedWsId}` : "/";
    const wsCrumb: Crumb = { label: wsName, href: wsHref };

    if (pageCrumbs && pageCrumbs.length > 0) {
      return [wsCrumb, ...pageCrumbs];
    }

    const segs = pathname.split("/").filter(Boolean);
    if (segs.length === 0) return [wsCrumb];

    if (segs[0] === "docs") {
      const rest: Crumb[] = [{ label: "Docs", href: "/docs" }];
      for (let i = 1; i < segs.length; i++) {
        rest.push({ label: titleCase(segs[i]) });
      }
      return [{ label: "stash", href: "/" }, ...rest];
    }

    if (segs[0] === "workspaces" && segs[1]) {
      return [wsCrumb];
    }

    const first = SEGMENT_LABELS[segs[0]];
    if (first) {
      return [
        wsCrumb,
        {
          label: first.label,
          href: selectedWsId ? `${first.href}?ws=${selectedWsId}` : first.href,
        },
      ];
    }
    return [wsCrumb, { label: titleCase(segs[0]) }];
  }, [pageCrumbs, pathname, selectedWsId, workspaces]);

  const displayName = user.display_name || user.name;
  const handle = user.display_name ? user.name : null;
  const initial = (displayName || "?")[0].toUpperCase();

  return (
    <div className="sticky top-0 z-10 flex h-12 items-center justify-between border-b border-border bg-base px-6">
      <nav className="flex min-w-0 items-center gap-2 text-[12px] text-muted">
        {crumbs.map((c, i) => {
          const isLast = i === crumbs.length - 1;
          const className =
            "truncate transition-colors " +
            (isLast
              ? "font-medium text-foreground"
              : "text-muted hover:text-foreground");
          return (
            <div key={i} className="flex items-center gap-2">
              {i > 0 && <span className="text-muted">/</span>}
              {!isLast && c.href ? (
                <Link href={c.href} className={className}>
                  {c.label}
                </Link>
              ) : !isLast && c.onClick ? (
                <button type="button" onClick={c.onClick} className={className}>
                  {c.label}
                </button>
              ) : (
                <span className={className}>{c.label}</span>
              )}
            </div>
          );
        })}
      </nav>
      <div className="flex items-center gap-3">
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
