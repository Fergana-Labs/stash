"use client";

import { Fragment, useEffect, useRef, useState, type ComponentType } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Bot, FolderTree, MessagesSquare, GraduationCap, Home, Wrench, Settings } from "lucide-react";
import HopperIcon from "@/components/HopperIcon";
import { cn } from "@/lib/utils";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { useWorkspace, type RailSection } from "@/lib/workspace-store";
import type { User } from "@/lib/types";

type RailItem = {
  key: RailSection;
  label: string;
  icon: ComponentType<{ className?: string }>;
  match: (p: string) => boolean;
};

// Primary sections — each opens its own explorer panel (see workspace-shell).
const PRIMARY: RailItem[] = [
  { key: "home", label: "Home", icon: Home, match: (p) => p === "/" },
  { key: "hopper", label: "Hopper", icon: HopperIcon, match: (p) => p.startsWith("/hopper") },
  { key: "files", label: "VFS", icon: FolderTree, match: (p) => p === "/files" || p.startsWith("/f/") || p.startsWith("/p/") || p.startsWith("/folders/") || p.startsWith("/tables/") },
  { key: "sessions", label: "Sessions", icon: MessagesSquare, match: (p) => p.startsWith("/sessions") || p.startsWith("/session-folders") },
  { key: "skills", label: "Skills", icon: GraduationCap, match: (p) => p.startsWith("/skills") },
  { key: "tools", label: "Tools", icon: Wrench, match: (p) => p.startsWith("/tools") || p.startsWith("/integrations") },
  { key: "agents", label: "Chat", icon: Bot, match: (p) => p.startsWith("/agents") },
];

// Home is the memory dashboard — the divider separates it from the VFS
// sections. Hopper opens that group because it is the way in: everything
// dropped there lands in the VFS. Chat sits last: it's a lens over the stash,
// not a place in it.
// Apps lives at /apps. The VM has NO entry point since it left this rail: the
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
      <button
        onClick={() => setOpen((o) => !o)}
        title={user.email ?? user.name}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-500 text-[12px] font-semibold text-white hover:ring-2 hover:ring-brand-200"
      >
        {user.display_name[0].toUpperCase()}
      </button>
      {open && (
        <div role="menu" className="absolute bottom-0 left-full z-40 ml-2 w-56 overflow-hidden rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg">
          <div className="border-b border-border px-3 py-1.5 text-[11px] text-muted-foreground">
            Signed in as <span className="break-all text-foreground">{user.email ?? user.name}</span>
          </div>
          <Link href="/settings" onClick={() => setOpen(false)} className="block px-3 py-1.5 text-foreground hover:bg-raised">
            Account settings
          </Link>
          <button onClick={() => { setOpen(false); onLogout(); }} className="block w-full px-3 py-1.5 text-left text-foreground hover:bg-raised">
            Sign out
          </button>
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
  const requestedSection = searchParams.get("section");

  function selectSection(section: RailSection) {
    // VFS resumes where the user left off; clicking it while already in the
    // VFS zooms out to the full-screen lens.
    if (section === "files") {
      const filesItem = PRIMARY.find((i) => i.key === "files")!;
      const alreadyInVfs = requestedSection === "files" || (!requestedSection && filesItem.match(pathname));
      setRailSection(section);
      router.replace(alreadyInVfs ? "/files" : useWorkspace.getState().lastVfsUrl ?? "/files");
      return;
    }
    // Every other section is a page; the rail is pure navigation.
    const LANDING: Record<Exclude<RailSection, "files" | "computer">, string> = {
      home: "/",
      hopper: "/hopper",
      agents: "/agents",
      sessions: "/sessions",
      skills: "/skills",
      tools: "/tools",
    };
    setRailSection(section);
    router.replace(LANDING[section as keyof typeof LANDING]);
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
