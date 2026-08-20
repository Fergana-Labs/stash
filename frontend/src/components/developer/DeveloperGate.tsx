"use client";

import { useEffect, useState } from "react";

import { PageHeading } from "@/components/developer/DocsPrimitives";
import { activateDeveloperPlatform, listMyWorkspaces } from "@/lib/api";
import { getScope, setScope } from "@/lib/scope-store";
import type { Workspace } from "@/lib/types";

/**
 * Wraps every /developer page: renders children only when the selected
 * context is a Developer Platform workspace. Otherwise shows the entry screen —
 * enter an existing one, or activate the platform (the tiny onboarding from the
 * shaping doc). Entering stamps Scope.view = "developer", which is what flips
 * the app chrome to the platform shell.
 */
export default function DeveloperGate({ children }: { children: React.ReactNode }) {
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [activating, setActivating] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activateError, setActivateError] = useState<string | null>(null);

  const scope = getScope();
  const inPlatform =
    scope?.view === "developer" &&
    workspaces?.some(
      (w) => w.scope_user_id === scope.scope_user_id && w.external_wiki_folder_id !== null,
    );

  useEffect(() => {
    listMyWorkspaces()
      .then(setWorkspaces)
      .catch((e) =>
        setLoadError(e instanceof Error ? e.message : "Failed to load your workspaces"),
      );
  }, []);

  // Which workspaces exist decides what this screen offers, so an unreachable
  // list is never treated as "you have none".
  if (loadError) {
    return (
      <p className="text-[15px] text-error">Couldn&apos;t load your workspaces: {loadError}</p>
    );
  }

  if (workspaces === null) {
    return <p className="text-[15px] text-muted-foreground">Loading…</p>;
  }

  if (inPlatform) return <>{children}</>;

  function enter(w: Workspace) {
    setScope({ scope_user_id: w.scope_user_id, name: w.name, view: "developer" });
    window.location.assign("/developer");
  }

  async function activate() {
    setActivating(true);
    setActivateError(null);
    try {
      enter(await activateDeveloperPlatform());
    } catch (e) {
      setActivateError(e instanceof Error ? e.message : "Could not set up the platform");
    } finally {
      setActivating(false);
    }
  }

  const active = workspaces.filter((w) => w.external_wiki_folder_id !== null);
  return (
    <div className="max-w-xl">
      <PageHeading title="Developer Platform">
        Run Stash for your product&apos;s users: each tenant is one of them — a company or
        one person — with its own
        private memory, and your agents share one anonymized wiki distilled across all of them.
      </PageHeading>
      {active.length > 0 && (
        <div className="mb-6 overflow-hidden rounded border border-border bg-surface">
          {active.map((w) => (
            <button
              key={w.id}
              onClick={() => enter(w)}
              className="flex w-full items-center gap-3 border-b border-border px-5 py-4 text-left text-[15px] transition-colors last:border-b-0 hover:bg-raised"
            >
              <span className="font-medium text-foreground">{w.name}</span>
              <span className="ml-auto text-[13px] text-muted-foreground">Enter</span>
            </button>
          ))}
        </div>
      )}
      <button
        onClick={activate}
        disabled={activating}
        className="rounded-sm bg-brand-500 px-4 py-2 text-[14px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50"
      >
        {activating ? "Setting up…" : "Set up the Developer Platform"}
      </button>
      {activateError && <p className="mt-3 text-[14px] text-error">{activateError}</p>}
    </div>
  );
}
