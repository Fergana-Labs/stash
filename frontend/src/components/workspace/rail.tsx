"use client";

import { Fragment } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BarChart3, FolderTree, MessagesSquare, GraduationCap, Home, Orbit, Settings } from "lucide-react";
import AccountMenu from "@/components/workspace/account-menu";
import { cn } from "@/lib/utils";
import { useWorkspace, type RailSection } from "@/lib/workspace-store";
import type { User } from "@/lib/types";

type RailItem = { key: RailSection; label: string; icon: typeof Home; match: (p: string) => boolean };

// Primary sections — each opens its own explorer panel (see workspace-shell).
const PRIMARY: RailItem[] = [
  { key: "home", label: "Home", icon: Home, match: (p) => p === "/" },
  { key: "skills", label: "Skills", icon: GraduationCap, match: (p) => p.startsWith("/skills") },
  { key: "sessions", label: "Sessions", icon: MessagesSquare, match: (p) => p.startsWith("/sessions") && p !== "/sessions/analytics" },
  { key: "analytics", label: "Session Analytics", icon: BarChart3, match: (p) => p === "/sessions/analytics" },
  { key: "files", label: "Files", icon: FolderTree, match: (p) => p === "/files" || p.startsWith("/f/") || p.startsWith("/p/") || p.startsWith("/folders/") || p.startsWith("/tables/") },
  { key: "viz", label: "Viz", icon: Orbit, match: (p) => p === "/viz" },
];

// Home is the memory dashboard — the divider separates it from the VFS
// sections. Apps lives at /apps. The VM has NO entry point since it left this rail: the
// explorer's Home root is the only thing that lists it, and that root only
// renders once you are already inside the VM section (?section=computer).
const DIVIDER_AFTER_INDEX = 0;

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
    <button
      type="button"
      onClick={onClick}
      aria-label={item.label}
      className={cn(
        "flex w-full flex-col items-center gap-1 rounded-lg py-2 transition-colors",
        active
          ? "bg-brand-500/12 text-brand-600"
          : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground",
      )}
    >
      <Icon className="h-[18px] w-[18px]" />
      <span className="text-[10px] font-medium leading-none">{item.label}</span>
    </button>
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
  const requestedSection = searchParams.get("section");
  const items = PRIMARY;

  function selectSection(section: RailSection) {
    // Files is the flat, full-stash index. Item routes still use the VFS
    // workbench, but the primary navigation always returns to that index.
    if (section === "files") {
      setRailSection(section);
      router.replace("/files");
      return;
    }
    // Every other section is a page; the rail is pure navigation.
    const LANDING: Record<Exclude<RailSection, "files" | "computer" | "tools">, string> = {
      home: "/",
      skills: "/skills",
      sessions: "/sessions",
      analytics: "/sessions/analytics",
      viz: "/viz",
    };
    setRailSection(section);
    router.replace(LANDING[section as keyof typeof LANDING]);
  }

  return (
    <div className="flex w-[74px] shrink-0 flex-col items-center gap-1 border-r border-sidebar-border bg-rail px-1.5 py-2.5">
      {items.map((item, i) => (
        <Fragment key={item.key}>
          <RailButton
            item={item}
            active={requestedSection === item.key || (!requestedSection && item.match(pathname))}
            onClick={() => selectSection(item.key)}
          />
          {i === DIVIDER_AFTER_INDEX && (
            <div className="my-1 h-px w-7 bg-[var(--divider-color)]" />
          )}
        </Fragment>
      ))}
      <div className="mt-auto flex w-full flex-col items-center gap-1">
        <Link
          href="/settings"
          aria-label="Settings"
          className={cn(
            "flex w-full flex-col items-center gap-1 rounded-lg py-2 transition-colors",
            pathname.startsWith("/settings")
              ? "bg-brand-500/12 text-brand-600"
              : "text-sidebar-foreground/45 hover:bg-sidebar-accent hover:text-sidebar-foreground",
          )}
        >
          <Settings className="h-[18px] w-[18px]" />
          <span className="text-[10px] font-medium leading-none">Settings</span>
        </Link>
        <AccountMenu user={user} onLogout={onLogout} />
      </div>
    </div>
  );
}
