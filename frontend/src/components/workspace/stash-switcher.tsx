"use client";

// The workspace-analogy stash switcher: one world at a time, named in the
// chrome, all others behind a dropdown — Slack's workspace menu, not its
// channel list. Switching swaps the scope header and remounts the content
// area (workspace-shell keys on the scope) — same mechanics as the
// channel-sidebar branch, so only the presentation differs.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Check, ChevronDown, CircleUser, Plus } from "lucide-react";
import { createStash, listMyStashes, listMyWorkspaces } from "@/lib/api";
import { getScope, setScope, useScope } from "@/lib/scope-store";
import type { Scope, UserStash, Workspace } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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

/** Stable color per stash so the menu's worlds are tellable apart at a glance. */
const DOT_COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
];
function dotColor(id: string): string {
  let hash = 0;
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return DOT_COLORS[Math.abs(hash) % DOT_COLORS.length];
}

function monogram(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 2);
  return (words[0][0] + words[1][0]).toUpperCase();
}

function Mono({ name, color }: { name: string; color: string }) {
  return (
    <span
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[10.5px] font-semibold text-white"
      style={{ background: color }}
    >
      {monogram(name)}
    </span>
  );
}

export default function StashSwitcher() {
  const router = useRouter();
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
    // Entering a world lands on its front door.
    router.push("/");
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
  const activeStash = stashes.find((s) => s.scope_user_id === activeId);
  const unreadElsewhere = stashes.some((s) => s.scope_user_id !== activeId && isUnread(s));

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex h-8 items-center gap-2 rounded-full border border-border bg-surface px-2 pr-3 text-[13px] font-medium text-foreground transition-colors hover:bg-raised">
        {activeStash ? (
          <Mono name={activeStash.name} color={dotColor(activeStash.id)} />
        ) : (
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-raised">
            <CircleUser className="h-4 w-4 text-muted-foreground" />
          </span>
        )}
        <span className="max-w-[160px] truncate">{scope?.name ?? "Personal"}</span>
        {/* A quiet signal that some other world has news — the one concession
            the workspace model makes to glanceability. */}
        {unreadElsewhere && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />}
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel className="text-[11px] text-muted-foreground">
          Stashes
        </DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => select(null)} className="gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-raised">
            <CircleUser className="h-4 w-4 text-muted-foreground" />
          </span>
          <span className="min-w-0 flex-1 truncate text-[13px]">Personal</span>
          {activeId === null && <Check className="h-4 w-4 shrink-0 text-brand-500" />}
        </DropdownMenuItem>
        {stashes.map((s) => {
          const active = activeId === s.scope_user_id;
          const unread = !active && isUnread(s);
          return (
            <DropdownMenuItem
              key={s.id}
              onSelect={() => select({ scope_user_id: s.scope_user_id, name: s.name })}
              className="gap-2"
            >
              <Mono name={s.name} color={dotColor(s.id)} />
              <span className={cn("min-w-0 flex-1 truncate text-[13px]", unread && "font-semibold")}>
                {s.name}
              </span>
              {unread && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />}
              {s.item_count > 0 && (
                <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">
                  {s.item_count}
                </span>
              )}
              {active && <Check className="h-4 w-4 shrink-0 text-brand-500" />}
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuItem onSelect={newStash} className="gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-dashed border-border">
            <Plus className="h-3.5 w-3.5 text-muted-foreground" />
          </span>
          <span className="text-[13px] text-muted-foreground">New stash…</span>
        </DropdownMenuItem>
        {workspaces.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-[11px] text-muted-foreground">
              Workspaces
            </DropdownMenuLabel>
            {workspaces.map((w) => (
              <DropdownMenuItem
                key={w.id}
                onSelect={() => select({ scope_user_id: w.scope_user_id, name: w.name })}
                className="gap-2"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-raised">
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px]">{w.name}</span>
                {activeId === w.scope_user_id && (
                  <Check className="h-4 w-4 shrink-0 text-brand-500" />
                )}
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
