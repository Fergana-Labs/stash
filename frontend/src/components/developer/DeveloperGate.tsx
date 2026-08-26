"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen, TerminalSquare, Users } from "lucide-react";

import { StashIcon } from "@/components/SkillIcons";
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
      // Stay disabled: enter() navigates, and every activate call creates a
      // fresh workspace — re-enabling mid-navigation invited a second click
      // and a duplicate "<name> (Developer)" workspace.
    } catch (e) {
      setActivateError(e instanceof Error ? e.message : "Could not set up the platform");
      setActivating(false);
    }
  }

  const active = workspaces.filter((w) => w.external_wiki_folder_id !== null);
  // A full-viewport takeover, deliberately outside the app chrome: entering
  // the platform is a doorway into the console's own world, and the gate
  // already wears that world's surface tokens.
  return (
    <div data-surface="developer" className="fixed inset-0 z-50 overflow-y-auto bg-base">
      <div className="flex items-center justify-between px-6 py-5 sm:px-10">
        <div className="flex items-center gap-3">
          <StashIcon className="h-6 w-6" />
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Developer Platform
          </span>
        </div>
        <Link
          href="/"
          className="text-[13.5px] text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Back to Stash
        </Link>
      </div>

      <div className="flex min-h-[calc(100vh-140px)] items-center justify-center px-6 py-10">
        <div className="w-full max-w-xl">
          <h1 className="text-[34px] font-semibold leading-[1.15] tracking-tight text-foreground text-balance">
            Run Stash for your product&apos;s users
          </h1>
          <p className="mt-4 max-w-lg text-[16px] leading-7 text-dim">
            Each of your users — a company or one person — gets memory of their own, and
            your agents share what they learn.
          </p>

          <ul className="mt-10 space-y-5">
            <Feature icon={Users} title="Per-user memory">
              Every user gets a private wiki only their agent reads — one field,{" "}
              <code className="rounded bg-raised px-1 font-mono text-[12.5px]">user_id</code>,
              is the isolation boundary.
            </Feature>
            <Feature icon={BookOpen} title="One shared brain">
              A curator distills every user&apos;s sessions into a single anonymized wiki
              all your agents read.
            </Feature>
            <Feature icon={TerminalSquare} title="Agent-first setup">
              Copy one prompt into your coding agent and it wires your app — no SDK
              required.
            </Feature>
          </ul>

          {active.length > 0 && (
            <div className="mt-10 overflow-hidden rounded-lg border border-border bg-surface">
              {active.map((w) => (
                <button
                  key={w.id}
                  onClick={() => enter(w)}
                  className="flex w-full items-center gap-3 border-b border-border px-5 py-3.5 text-left text-[14.5px] transition-colors last:border-b-0 hover:bg-raised"
                >
                  <span className="font-medium text-foreground">{w.name}</span>
                  <span className="ml-auto text-[13px] text-muted-foreground">Enter →</span>
                </button>
              ))}
            </div>
          )}

          <button
            onClick={activate}
            disabled={activating}
            className="mt-10 w-full rounded-lg bg-brand-500 px-5 py-3 text-[15px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50 sm:w-auto sm:px-8"
          >
            {activating
              ? "Setting up…"
              : active.length > 0
                ? "Set up another workspace"
                : "Set up the Developer Platform"}
          </button>
          {activateError && <p className="mt-3 text-[14px] text-error">{activateError}</p>}
        </div>
      </div>
    </div>
  );
}

function Feature({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Users;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="flex gap-3">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-brand-500/10 text-brand-600">
        <Icon className="h-4 w-4" />
      </span>
      <span className="text-[13.5px] leading-5 text-muted-foreground">
        <span className="font-medium text-foreground">{title}</span> — {children}
      </span>
    </li>
  );
}
