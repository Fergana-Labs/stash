"use client";

import { useEffect, useState } from "react";
import { Building2, TerminalSquare } from "lucide-react";

import { activateDeveloperPlatform, listMyWorkspaces } from "@/lib/api";
import { getScope, setScope } from "@/lib/scope-store";
import type { Workspace } from "@/lib/types";

/**
 * Wraps every /developer page: renders children only when the selected
 * context is a Developer Console. Otherwise shows the entry screen —
 * enter an existing console, or activate the platform (the tiny onboarding
 * from the shaping doc). Entering stamps Scope.view = "developer", which is
 * what flips the app chrome to the devtool rail.
 */
export default function DeveloperGate({ children }: { children: React.ReactNode }) {
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [activating, setActivating] = useState(false);

  const scope = getScope();
  const inConsole =
    scope?.view === "developer" &&
    workspaces?.some(
      (w) => w.scope_user_id === scope.scope_user_id && w.external_wiki_folder_id !== null,
    );

  useEffect(() => {
    listMyWorkspaces()
      .then(setWorkspaces)
      .catch(() => setWorkspaces([]));
  }, []);

  if (workspaces === null) {
    return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;
  }

  if (inConsole) return <>{children}</>;

  function enter(w: Workspace) {
    setScope({ scope_user_id: w.scope_user_id, name: w.name, view: "developer" });
    window.location.assign("/developer");
  }

  async function activate() {
    setActivating(true);
    try {
      const ws = await activateDeveloperPlatform();
      enter(ws);
    } finally {
      setActivating(false);
    }
  }

  const consoles = workspaces.filter((w) => w.external_wiki_folder_id !== null);
  return (
    <div className="mx-auto max-w-xl p-8">
      <div className="mb-2 flex items-center gap-2">
        <TerminalSquare className="h-6 w-6 text-brand-500" />
        <h1 className="text-xl font-semibold">Developer Console</h1>
      </div>
      <p className="mb-6 text-sm text-muted-foreground">
        Run Stash for your product&apos;s customers: each customer is an org with its
        own private memory, and your agents share one anonymized wiki distilled
        across all of them.
      </p>
      {consoles.map((w) => (
        <button
          key={w.id}
          onClick={() => enter(w)}
          className="mb-2 flex w-full items-center gap-2 rounded-lg border border-border bg-surface px-4 py-3 text-left text-sm hover:bg-raised"
        >
          <Building2 className="h-4 w-4 text-brand-500" />
          <span className="font-medium">{w.name}</span>
          <span className="ml-auto text-xs text-muted-foreground">Enter console</span>
        </button>
      ))}
      <button
        onClick={activate}
        disabled={activating}
        className="mt-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
      >
        {activating ? "Setting up…" : "Set up a Developer Console"}
      </button>
    </div>
  );
}
