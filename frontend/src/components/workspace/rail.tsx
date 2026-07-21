"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Bot, FolderTree, MessagesSquare, GraduationCap, Brain, Monitor, Wrench, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { Button } from "@/components/ui/button";
import { useWorkspace, type RailSection } from "@/lib/workspace-store";
import type { User } from "@/lib/types";

type RailItem = { key: RailSection; label: string; icon: typeof Bot; match: (p: string) => boolean };

// Primary sections — each opens its own explorer panel (see workspace-shell).
const PRIMARY: RailItem[] = [
  { key: "agents", label: "Agents", icon: Bot, match: (p) => p.startsWith("/agents") },
  { key: "files", label: "Files", icon: FolderTree, match: (p) => p === "/files" || p.startsWith("/file/") || p.startsWith("/page/") || p.startsWith("/folders/") || p.startsWith("/tables/") },
  { key: "sessions", label: "Sessions", icon: MessagesSquare, match: (p) => p.startsWith("/sessions") || p.startsWith("/session-folders") },
  { key: "skills", label: "Skills", icon: GraduationCap, match: (p) => p.startsWith("/skills") },
  { key: "memory", label: "Memory", icon: Brain, match: (p) => p.startsWith("/memory") },
  { key: "tools", label: "Tools", icon: Wrench, match: (p) => p.startsWith("/tools") || p.startsWith("/integrations") },
  { key: "computer", label: "VM", icon: Monitor, match: (p) => p.startsWith("/computer") },
];

const TOP_LEVEL_ROUTES = ["/files", "/sessions", "/skills", "/memory", "/tools", "/agents", "/computer"];

const ROUTES: Record<RailSection, string> = {
  agents: "/agents",
  files: "/files",
  sessions: "/sessions",
  skills: "/skills",
  memory: "/memory",
  tools: "/tools",
  computer: "/computer",
};

function RailButton({
  item,
  active,
  onClick,
}: {
  item: RailItem;
  active: boolean;
  onClick: () => void;
}) {
  const Icon = item.icon;
  return (
    <Button
      variant="ghost"
      onClick={onClick}
      aria-label={item.label}
      className={cn(
        "h-auto w-full flex-col gap-1 rounded-lg py-2 font-normal",
        active
          ? "bg-brand-500/12 text-brand-600"
          : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground",
      )}
    >
      <Icon className="h-[18px] w-[18px]" />
      <span className="text-[10px] font-medium leading-none">{item.label}</span>
    </Button>
  );
}

/** Bottom-left account control — avatar opens a small menu (settings + sign out).
 *  This is the single home for account actions (removed from the top bar). */
function AccountMenu({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEscapeKey(open, () => setOpen(false));
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <Button
        variant="default"
        size="icon"
        onClick={() => setOpen((o) => !o)}
        title={user.email ?? user.name}
        className="rounded-full bg-brand-500 text-xs font-semibold text-white hover:ring-2 hover:ring-brand-200"
      >
        {user.display_name[0].toUpperCase()}
      </Button>
      {open && (
        <div role="menu" className="absolute bottom-0 left-full z-40 ml-2 w-56 overflow-hidden rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg">
          <div className="border-b border-border px-3 py-1.5 text-[11px] text-muted-foreground">
            Signed in as <span className="break-all text-foreground">{user.email ?? user.name}</span>
          </div>
          <Link href="/settings" onClick={() => setOpen(false)} className="block px-3 py-1.5 text-foreground hover:bg-raised">
            Account settings
          </Link>
          <Button variant="ghost" onClick={() => { setOpen(false); onLogout(); }} className="h-auto block w-full justify-start px-3 py-1.5 text-left text-[13px] font-normal text-foreground hover:bg-raised">
            Sign out
          </Button>
        </div>
      )}
    </div>
  );
}

/** The icon rail — the workspace's primary nav. Icon + label per section; each
 *  primary section shows its own explorer. Search lives in the top bar; account
 *  actions live on the bottom-left avatar. */
export default function Rail({ user, onLogout }: { user: User; onLogout: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const setRailSection = useWorkspace((s) => s.setRailSection);
  const setExplorerAtRoot = useWorkspace((s) => s.setExplorerAtRoot);
  const requestedSection = searchParams.get("section");

  function selectSection(section: RailSection) {
    setRailSection(section);
    setExplorerAtRoot(false);
    const targetRoute = ROUTES[section];
    
    // Check if current path is a top-level route (e.g. /files, /sessions) or outside workspace
    const isTopLevel =
      TOP_LEVEL_ROUTES.includes(pathname) ||
      !PRIMARY.some((item) => item.match(pathname));

    if (isTopLevel) {
      router.replace(targetRoute);
      return;
    }

    // We are on a deep link like /p/123. If clicked section matches current path, strip query params.
    const item = PRIMARY.find((s) => s.key === section);
    if (item?.match(pathname)) {
      router.replace(pathname);
      return;
    }

    // Otherwise, set the explorer section query parameter.
    const params = new URLSearchParams(searchParams);
    params.set("section", section);
    router.replace(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="flex w-[74px] shrink-0 flex-col items-center gap-1 border-r border-sidebar-border bg-rail px-1.5 py-2.5">
      {PRIMARY.map((item, i) => (
        <Fragment key={item.key}>
          <RailButton
            item={item}
            active={requestedSection === item.key || (!requestedSection && item.match(pathname))}
            onClick={() => selectSection(item.key)}
          />
          {/* Agents (chat) is set apart from the VFS sections below. */}
          {i === 0 && <div className="my-1 h-px w-7 bg-[var(--divider-color)]" />}
        </Fragment>
      ))}
      <div className="mt-auto flex w-full flex-col items-center gap-1">
        <AccountMenu user={user} onLogout={onLogout} />
      </div>
    </div>
  );
}
