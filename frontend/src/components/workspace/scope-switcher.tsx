"use client";

import { useEffect, useState } from "react";
import { Building2, Check, ChevronDown, CircleUser } from "lucide-react";
import { listMyWorkspaces } from "@/lib/api";
import { getScope, setScope, useScope } from "@/lib/scope-store";
import type { Scope, Workspace } from "@/lib/types";
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
 * personal stash, or a workspace's shared knowledge base. Hidden entirely for
 * users who belong to no workspace (nearly everyone), so the chrome only grows
 * a control when there's actually a choice to make.
 *
 * Scope-dependent data is fetched ad hoc by ~every view (no SWR/react-query
 * cache to invalidate), so switching reloads the app rather than trying to
 * chase down each in-flight useEffect.
 */
export default function ScopeSwitcher() {
  const scope = useScope();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);

  useEffect(() => {
    listMyWorkspaces()
      .then((mine) => {
        setWorkspaces(mine);
        // The scope outlives the membership that justified it: someone removed
        // from a workspace would otherwise keep stamping a scope the backend
        // now 403s, with the switcher gone and no way back to Personal.
        const selected = getScope();
        if (selected && !mine.some((w) => w.scope_user_id === selected.scope_user_id)) {
          setScope(null);
        }
      })
      .catch(() => setWorkspaces([]));
  }, []);

  if (workspaces.length === 0) return null;

  function select(next: Scope | null) {
    if ((next?.scope_user_id ?? null) === (scope?.scope_user_id ?? null)) return;
    setScope(next);
    window.location.reload();
  }

  const inWorkspace = scope !== null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors",
          inWorkspace
            ? "border-brand-300 bg-brand-500/12 text-brand-600 hover:bg-brand-500/20"
            : "border-border bg-surface text-foreground hover:bg-raised",
        )}
      >
        {inWorkspace ? (
          <Building2 className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <CircleUser className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="max-w-[160px] truncate">{scope?.name ?? "Personal"}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60">
        <DropdownMenuLabel className="text-[11px] text-muted-foreground">
          Scope
        </DropdownMenuLabel>
        <ScopeItem
          icon={<CircleUser className="h-4 w-4 text-muted-foreground" />}
          label="Personal"
          detail="Your own stash"
          selected={!inWorkspace}
          onSelect={() => select(null)}
        />
        <DropdownMenuSeparator />
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
