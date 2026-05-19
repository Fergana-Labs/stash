"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "../components/AppShell";
import { BasicPageSkeleton, HomeSkeleton } from "../components/SkeletonStates";
import { useAuth } from "../hooks/useAuth";
import { joinWorkspace, listMyWorkspaces } from "../lib/api";
import { resetStashNavigationCache } from "../lib/stashNavigationCache";
import type { Workspace } from "../lib/types";

function EmptyHome({
  onJoin,
  joinCode,
  onJoinCodeChange,
  joining,
  error,
}: {
  onJoin: (event: FormEvent) => void;
  joinCode: string;
  onJoinCodeChange: (next: string) => void;
  joining: boolean;
  error: string;
}) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-8 py-12">
      {error ? (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {error}
        </div>
      ) : null}
      <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
        Welcome
      </p>
      <h1 className="font-display text-[34px] font-bold tracking-tight text-foreground">
        Your workspace home
      </h1>
      <p className="max-w-[720px] text-[14.5px] leading-relaxed text-muted">
        Workspaces are the home for agent sessions, Files, and Stashes.
        Create one to get started or join one with an invite code.
      </p>

      <div className="rounded-lg border border-dashed border-border bg-surface/60 p-4">
        <h2 className="text-[16px] font-semibold text-foreground">Get started</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link
            href="/workspaces/new"
            className="rounded-md bg-[var(--color-brand-600)] px-3 py-2 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)]"
          >
            Create a workspace
          </Link>
        </div>
      </div>

      <form onSubmit={onJoin} className="rounded-lg border border-border bg-surface p-4">
        <h2 className="text-[16px] font-semibold text-foreground">Join by invite code</h2>
        <p className="mt-1 text-[12.5px] text-muted">
          Use a code from a workspace admin.
        </p>
        <div className="mt-3 flex gap-2">
          <input
            value={joinCode}
            onChange={(event) => onJoinCodeChange(event.target.value)}
            placeholder="Invite code"
            className="min-w-0 flex-1 rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
          />
          <button
            type="submit"
            disabled={joining || !joinCode.trim()}
            className="rounded-md border border-border bg-base px-3 py-2 text-[13px] font-medium text-foreground hover:bg-raised disabled:opacity-45"
          >
            {joining ? "Joining..." : "Join"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function Home() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, router, user]);

  if (loading || !user) {
    return <BasicPageSkeleton />;
  }

  return <LoggedInHome user={user} logout={logout} />;
}

function LoggedInHome({
  user,
  logout,
}: {
  user: NonNullable<ReturnType<typeof useAuth>["user"]>;
  logout: () => void;
}) {
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [joining, setJoining] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await listMyWorkspaces();
        if (cancelled) return;
        setWorkspaces(result.workspaces);
        if (result.workspaces.length === 0) return;

        // Prefer the workspace the user was in last time they had the app
        // open. AppSidebar writes this to localStorage every time you visit a
        // /workspaces/[id] route. If the cached id is no longer a workspace
        // the user belongs to (left, deleted, etc.), fall back to mine[0]
        // which the backend returns ordered by created_at DESC (newest first).
        let target = result.workspaces[0].id;
        try {
          const last = localStorage.getItem("stash_sidebar_last_workspace");
          if (last && result.workspaces.some((w) => w.id === last)) {
            target = last;
          }
        } catch {
          /* localStorage unavailable — fall back silently */
        }
        router.replace(`/workspaces/${target}`);
      } catch {
        if (!cancelled) setError("Failed to load workspaces");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (loading) {
    return (
      <AppShell user={user} onLogout={logout}>
        <HomeSkeleton />
      </AppShell>
    );
  }

  if (workspaces.length > 0) {
    return (
      <AppShell user={user} onLogout={logout}>
        <HomeSkeleton />
      </AppShell>
    );
  }

  async function handleJoin(event: FormEvent) {
    event.preventDefault();
    if (!joinCode.trim()) return;

    setJoining(true);
    try {
      const workspace = await joinWorkspace(joinCode.trim());
      resetStashNavigationCache();
      router.push(`/workspaces/${workspace.id}`);
    } catch {
      setError("Failed to join workspace");
    } finally {
      setJoining(false);
    }
  }

  return (
    <AppShell user={user} onLogout={logout}>
      <EmptyHome
        onJoin={handleJoin}
        joinCode={joinCode}
        onJoinCodeChange={setJoinCode}
        joining={joining}
        error={error}
      />
    </AppShell>
  );
}
