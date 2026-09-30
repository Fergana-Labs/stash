"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Settings } from "lucide-react";
import AccountMenu from "@/components/workspace/account-menu";
import { cn } from "@/lib/utils";
import type { User } from "@/lib/types";

const PRIMARY = [
  { label: "Traces", href: "/reward-models", match: (path: string) => path === "/reward-models" || path.startsWith("/reward-models/traces/") },
  { label: "Reward models", href: "/reward-models/models", match: (path: string) => path.startsWith("/reward-models/models") || path.startsWith("/reward-models/gepa/") },
  { label: "Skills", href: "/skills", match: (path: string) => path === "/skills" || path.startsWith("/skills/") },
];

export default function RewardRail({ user, onLogout }: { user: User; onLogout: () => void }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const inSkillFolder = searchParams.get("section") === "skills";

  return (
    <aside className="flex w-40 shrink-0 flex-col border-r border-sidebar-border bg-rail px-2 py-3">
      <nav aria-label="Main navigation" className="flex flex-col gap-1">
        {PRIMARY.map((item) => {
          const active = item.match(pathname) || (item.href === "/skills" && inSkillFolder);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "px-3 py-2 text-[13px] font-medium transition-colors",
                active ? "bg-brand-500/12 text-brand-600" : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground",
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto flex flex-col gap-2">
        <Link
          href="/settings"
          aria-current={pathname.startsWith("/settings") ? "page" : undefined}
          className={cn("flex items-center gap-2 px-3 py-2 text-[13px] hover:bg-sidebar-accent", pathname.startsWith("/settings") ? "text-brand-600" : "text-sidebar-foreground/60")}
        >
          <Settings className="h-4 w-4" aria-hidden="true" />
          Settings
        </Link>
        <AccountMenu user={user} onLogout={onLogout} />
      </div>
    </aside>
  );
}
