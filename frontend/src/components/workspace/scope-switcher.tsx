"use client";

import { useEffect, useState } from "react";
import { Archive, Building2, Check, ChevronDown, CircleUser, Plus } from "lucide-react";
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

/**
 * Switches the scope every content request runs in: the signed-in user's
 * personal stash, one of their extra stashes (work, a client, a side
 * project), or a workspace's shared knowledge base. Always rendered — the
 * menu is also where new stashes are created.
 *
 * Scope-dependent data is fetched ad hoc by ~every view (no SWR/react-query
 * cache to invalidate), so switching reloads the app rather than trying to
 * chase down each in-flight useEffect.
 */
export default function ScopeSwitcher() {
  const scope = useScope();
  const [stashes, setStashes] = useState<UserStash[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);

  useEffect(() => {
    Promise.all([listMyStashes(), listMyWorkspaces()])
      .then(([myStashes, myWorkspaces]) => {
        setStashes(myStashes);
        setWorkspaces(myWorkspaces);
        // The scope outlives the membership that justified it: a deleted stash
        // or a lost workspace membership would otherwise keep stamping a scope
        // the backend now 403s, with no way back to Personal.
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
    if ((next?.scope_user_id ?? null) === (scope?.scope_user_id ?? null)) return;
    setScope(next);
    window.location.reload();
  }

  async function newStash() {
    const name = window.prompt("Name the new stash:");
    if (!name?.trim()) return;
    const stash = await createStash(name.trim());
    setScope({ scope_user_id: stash.scope_user_id, name: stash.name });
    window.location.reload();
  }

  const inScope = scope !== null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors",
          inScope
            ? "border-brand-300 bg-brand-500/12 text-brand-600 hover:bg-brand-500/20"
            : "border-border bg-surface text-foreground hover:bg-raised",
        )}
      >
        {inScope ? (
          <Archive className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <CircleUser className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="max-w-[160px] truncate">{scope?.name ?? "Personal"}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60">
        <DropdownMenuLabel className="text-[11px] text-muted-foreground">
          Stash
        </DropdownMenuLabel>
        <ScopeItem
          icon={<CircleUser className="h-4 w-4 text-muted-foreground" />}
          label="Personal"
          detail="Your own stash"
          selected={!inScope}
          onSelect={() => select(null)}
        />
        {stashes.map((s) => (
          <ScopeItem
            key={s.id}
            icon={<Archive className="h-4 w-4 text-brand-500" />}
            label={s.name}
            detail="Isolated stash"
            selected={scope?.scope_user_id === s.scope_user_id}
            onSelect={() => select({ scope_user_id: s.scope_user_id, name: s.name })}
          />
        ))}
        <DropdownMenuItem onSelect={newStash} className="gap-2">
          <span className="flex h-4 w-4 shrink-0 items-center justify-center">
            <Plus className="h-4 w-4 text-muted-foreground" />
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
              <ScopeItem
                key={w.id}
                icon={<Building2 className="h-4 w-4 text-brand-500" />}
                label={w.name}
                detail={w.domain}
                selected={scope?.scope_user_id === w.scope_user_id}
                onSelect={() => select({ scope_user_id: w.scope_user_id, name: w.name })}
              />
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ScopeItem({
  icon,
  label,
  detail,
  selected,
  onSelect,
}: {
  icon: React.ReactNode;
  label: string;
  detail: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <DropdownMenuItem onSelect={onSelect} className="gap-2">
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">{icon}</span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-[13px] text-foreground">{label}</span>
        <span className="truncate text-[11px] text-muted-foreground">{detail}</span>
      </span>
      {selected && <Check className="h-4 w-4 shrink-0 text-brand-500" />}
    </DropdownMenuItem>
  );
}
