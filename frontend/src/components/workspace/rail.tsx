"use client";

import { Fragment } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  FolderTree,
  MessagesSquare,
  GraduationCap,
  Home,
  Orbit,
  Settings,
} from "lucide-react";
import { useBreadcrumbsValue } from "@/components/BreadcrumbContext";
import AccountMenu from "@/components/workspace/account-menu";
import { cn } from "@/lib/utils";
import type { User } from "@/lib/types";

type RailSection =
  "home" | "skills" | "sessions" | "analytics" | "files" | "viz";
type RailItem = {
  key: RailSection;
  label: string;
  icon: typeof Home;
  match: (p: string) => boolean;
};

const PRIMARY: RailItem[] = [
  { key: "home", label: "Home", icon: Home, match: (p) => p === "/" },
  {
    key: "skills",
    label: "Skills",
    icon: GraduationCap,
    match: (p) => p.startsWith("/skills"),
  },
  {
    key: "sessions",
    label: "Sessions",
    icon: MessagesSquare,
    match: (p) => p.startsWith("/sessions") && p !== "/sessions/analytics",
  },
  {
    key: "analytics",
    label: "Usage",
    icon: BarChart3,
    match: (p) => p === "/sessions/analytics",
  },
  {
    key: "files",
    label: "Files",
    icon: FolderTree,
    match: (p) => p === "/files",
  },
  { key: "viz", label: "Themes", icon: Orbit, match: (p) => p === "/viz" },
];

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

export default function Rail({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const breadcrumbs = useBreadcrumbsValue();
  const contentArea = /^\/(f|p|folders|tables)\//.test(pathname)
    ? breadcrumbs?.[0]?.area
    : undefined;
  const items = PRIMARY;

  function selectSection(section: RailSection) {
    const landing: Record<RailSection, string> = {
      home: "/",
      skills: "/skills",
      sessions: "/sessions",
      analytics: "/sessions/analytics",
      files: "/files",
      viz: "/viz",
    };
    router.replace(landing[section]);
  }

  return (
    <div className="flex w-[74px] shrink-0 flex-col items-center gap-1 border-r border-sidebar-border bg-rail px-1.5 py-2.5">
      {items.map((item, i) => (
        <Fragment key={item.key}>
          <RailButton
            item={item}
            active={
              item.match(pathname) ||
              (item.key === "home" && contentArea === "memory") ||
              (item.key === "skills" && contentArea === "skills") ||
              (item.key === "files" && contentArea === "files")
            }
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
