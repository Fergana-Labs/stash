"use client";

import { useEffect, useState } from "react";
import { Building2, Check, ChevronDown, CircleUser, TerminalSquare } from "lucide-react";
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
 * The context switcher: one flat list of every context the user can stand in —
 * their personal stash, each workspace's shared knowledge base, and each
 * developer console (a workspace with the developer platform active). A flat
 * list rather than two toggles because the workspace × surface matrix is
 * sparse: most contexts don't have both faces, and a row simply doesn't
 * exist when the context doesn't.
 *
 * Scope-dependent data is fetched ad hoc by ~every view (no SWR/react-query
 * cache to invalidate), so switching reloads the app rather than trying to
 * chase down each in-flight useEffect.
 */
export default function ScopeSwitcher() {
  const scope = useScope();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load your workspaces"),
      );
  }, []);

  function select(next: Scope | null) {
    // Same workspace in a different view is still a switch — the console and
    // the internal knowledge base share a scope but not their chrome.
    const same =
      (next?.scope_user_id ?? null) === (scope?.scope_user_id ?? null) &&
      (next?.view ?? null) === (scope?.view ?? null);
    if (same) return;
    setScope(next);
    window.location.assign("/");
  }

  function enterConsole(w: Workspace) {
    setScope({ scope_user_id: w.scope_user_id, name: w.name, view: "developer" });
    window.location.assign("/developer");
  }

  const inWorkspace = scope !== null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors",
          // Inside the developer shell the pill goes monochrome with the rest
          // of the infra chrome; brand color belongs to the consumer app.
          scope?.view === "developer"
            ? "rounded-md border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-50"
            : inWorkspace
              ? "border-brand-300 bg-brand-500/12 text-brand-600 hover:bg-brand-500/20"
              : "border-border bg-surface text-foreground hover:bg-raised",
        )}
      >
        {scope?.view === "developer" ? (
          <TerminalSquare className="h-3.5 w-3.5 shrink-0" />
        ) : inWorkspace ? (
          <Building2 className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <CircleUser className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="max-w-[160px] truncate">
          {scope ? (scope.view === "developer" ? `${scope.name} Console` : scope.name) : "Personal"}
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
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
        {error ? (
          <>
            <DropdownMenuSeparator />
            <div className="px-2 py-1.5 text-[12px] text-destructive">
              Couldn&apos;t load your workspaces: {error}
            </div>
          </>
        ) : workspaces === null ? (
          <>
            <DropdownMenuSeparator />
            <div className="px-2 py-1.5 text-[12px] text-muted-foreground">Loading…</div>
          </>
        ) : (
          <WorkspaceScopes
            workspaces={workspaces}
            scope={scope}
            onSelect={select}
            onEnterConsole={enterConsole}
          />
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Every row that needs the workspace list, so the list is non-null here and
 *  "you have no console" is only ever said about a list that actually loaded. */
function WorkspaceScopes({
  workspaces,
  scope,
  onSelect,
  onEnterConsole,
}: {
  workspaces: Workspace[];
  scope: Scope | null;
  onSelect: (next: Scope | null) => void;
  onEnterConsole: (w: Workspace) => void;
}) {
  const consoles = workspaces.filter((w) => w.external_wiki_folder_id !== null);
  return (
    <>
      {workspaces.length > 0 && <DropdownMenuSeparator />}
      {workspaces.map((w) => (
        <ScopeItem
          key={w.id}
          icon={<Building2 className="h-4 w-4 text-brand-500" />}
          label={w.name}
          detail={w.domain ?? "invite-only workspace"}
          selected={scope?.scope_user_id === w.scope_user_id && scope?.view !== "developer"}
          onSelect={() => onSelect({ scope_user_id: w.scope_user_id, name: w.name })}
        />
      ))}
      <DropdownMenuSeparator />
      <DropdownMenuLabel className="text-[11px] text-muted-foreground">
        Developer
      </DropdownMenuLabel>
      {consoles.map((w) => (
        <ScopeItem
          key={`console-${w.id}`}
          icon={<TerminalSquare className="h-4 w-4 text-brand-500" />}
          label={`${w.name} Console`}
          detail="Orgs, memory, API keys"
          selected={scope?.scope_user_id === w.scope_user_id && scope?.view === "developer"}
          onSelect={() => onEnterConsole(w)}
        />
      ))}
      {consoles.length === 0 && (
        <ScopeItem
          icon={<TerminalSquare className="h-4 w-4 text-muted-foreground" />}
          label="Set up Developer Console"
          detail="Run Stash for your product's customers"
          selected={false}
          onSelect={() => {
            window.location.assign("/developer");
          }}
        />
      )}
    </>
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
