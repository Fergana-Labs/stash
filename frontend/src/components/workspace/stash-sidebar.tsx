"use client";

// The channel-style stash list — stashes analogized to Slack channels, not
// workspaces: all of them visible at once, cheap to glance, cheap to switch.
// Rows bold when a stash has activity you haven't looked at, the way unread
// channels do. Lives leftmost in the shell; switching swaps the scope header
// and remounts the content area (workspace-shell keys on the scope) — no page
// reload.

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Building2, CircleUser, Plus } from "lucide-react";
import { createStash, listMyStashes, listMyWorkspaces } from "@/lib/api";
import { getScope, setScope, useScope } from "@/lib/scope-store";
import type { Scope, UserStash, Workspace } from "@/lib/types";
import { scopeSwitchLanding } from "@/lib/workspace-routes";
import { cn } from "@/lib/utils";

const LAST_VIEWED_KEY = "stash_last_viewed";

function lastViewed(): Record<string, string> {
  const raw = localStorage.getItem(LAST_VIEWED_KEY);
  return raw ? JSON.parse(raw) : {};
}

function markViewed(scopeUserId: string) {
  const seen = lastViewed();
  seen[scopeUserId] = new Date().toISOString();
  localStorage.setItem(LAST_VIEWED_KEY, JSON.stringify(seen));
}

/** Stable color per stash so 20 clients are tellable apart at a glance. */
const DOT_COLORS = ["text-chart-1", "text-chart-2", "text-chart-3", "text-chart-4"];
function dotColor(id: string): string {
  let hash = 0;
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return DOT_COLORS[Math.abs(hash) % DOT_COLORS.length];
}

function Row({
  icon,
  label,
  count,
  active,
  unread,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  count?: number;
  active: boolean;
  unread?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2 py-[5px] text-left text-[13px]",
        active
          ? "bg-brand-500/12 text-brand-600"
          : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground",
      )}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">{icon}</span>
      <span className={cn("min-w-0 flex-1 truncate", unread && !active && "font-semibold text-sidebar-foreground")}>
        {label}
      </span>
      {unread && !active && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />}
      {count !== undefined && count > 0 && (
        <span className="shrink-0 font-mono text-[10.5px] text-sidebar-foreground/50">{count}</span>
      )}
    </button>
  );
}

export default function StashSidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const scope = useScope();
  const [stashes, setStashes] = useState<UserStash[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [seen, setSeen] = useState<Record<string, string>>({});

  useEffect(() => {
    setSeen(lastViewed());
    Promise.all([listMyStashes(), listMyWorkspaces()])
      .then(([myStashes, myWorkspaces]) => {
        setStashes(myStashes);
        setWorkspaces(myWorkspaces);
        // A deleted stash or lost workspace membership must not keep stamping
        // a scope the backend now 403s.
        const selected = getScope();
        const known = [
          ...myStashes.map((s) => s.scope_user_id),
          ...myWorkspaces.map((w) => w.scope_user_id),
        ];
        if (selected && !known.includes(selected.scope_user_id)) {
          setScope(null);
        }
      })
      .catch(() => {
        setStashes([]);
        setWorkspaces([]);
      });
  }, []);

  function select(next: Scope | null) {
    markViewed(next?.scope_user_id ?? "personal");
    setSeen(lastViewed());
    if ((next?.scope_user_id ?? null) === (scope?.scope_user_id ?? null)) return;
    setScope(next);
    // Keep your place: switching stashes stays in the section you were in.
    router.push(scopeSwitchLanding(pathname));
  }

  async function newStash() {
    const name = window.prompt("Name the new stash:");
    if (!name?.trim()) return;
    const stash = await createStash(name.trim());
    setStashes((prev) => [...prev, stash]);
    select({ scope_user_id: stash.scope_user_id, name: stash.name });
  }

  function isUnread(s: UserStash): boolean {
    if (!s.last_activity_at) return false;
    const viewedAt = seen[s.scope_user_id];
    return !viewedAt || new Date(s.last_activity_at) > new Date(viewedAt);
  }

  const activeId = scope?.scope_user_id ?? null;

  return (
    <div className="flex w-[184px] shrink-0 flex-col border-r border-sidebar-border bg-rail px-2 py-2.5">
      <div className="px-2 pb-1.5 font-mono text-[10.5px] uppercase tracking-wide text-sidebar-foreground/50">
        Stashes
      </div>
      <Row
        icon={<CircleUser className="h-4 w-4 text-sidebar-foreground/60" />}
        label="Personal"
        active={activeId === null}
        onClick={() => select(null)}
      />
      {stashes.map((s) => (
        <Row
          key={s.id}
          icon={
            <span className={dotColor(s.id)}>
              <span className="block h-2 w-2 rounded-full bg-current" />
            </span>
          }
          label={s.name}
          count={s.item_count}
          active={activeId === s.scope_user_id}
          unread={isUnread(s)}
          onClick={() => select({ scope_user_id: s.scope_user_id, name: s.name })}
        />
      ))}
      <button
        type="button"
        onClick={newStash}
        className="mt-0.5 flex w-full items-center gap-2 rounded-md px-2 py-[5px] text-left text-[13px] text-sidebar-foreground/50 hover:bg-sidebar-accent hover:text-sidebar-foreground"
      >
        <span className="flex h-4 w-4 shrink-0 items-center justify-center">
          <Plus className="h-3.5 w-3.5" />
        </span>
        New stash
      </button>
      {workspaces.length > 0 && (
        <>
          <div className="px-2 pb-1.5 pt-3 font-mono text-[10.5px] uppercase tracking-wide text-sidebar-foreground/50">
            Workspaces
          </div>
          {workspaces.map((w) => (
            <Row
              key={w.id}
              icon={<Building2 className="h-4 w-4 text-sidebar-foreground/60" />}
              label={w.name}
              active={activeId === w.scope_user_id}
              onClick={() => select({ scope_user_id: w.scope_user_id, name: w.name })}
            />
          ))}
        </>
      )}
    </div>
  );
}
