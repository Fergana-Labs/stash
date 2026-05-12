"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../../../components/AppShell";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../hooks/useAuth";
import { getStashSpine, getWorkspace, type StashSpine } from "../../../../lib/api";
import type { Workspace } from "../../../../lib/types";

export default function SessionsPage() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const { user, loading, logout } = useAuth();

  const [stash, setStash] = useState<Workspace | null>(null);
  const [spine, setSpine] = useState<StashSpine | null>(null);
  const [error, setError] = useState("");

  useBreadcrumbs([{ label: "Sessions" }], `${stashId}/sessions`);

  const load = useCallback(async () => {
    try {
      const [workspace, nextSpine] = await Promise.all([
        getWorkspace(stashId),
        getStashSpine(stashId),
      ]);
      setStash(workspace);
      setSpine(nextSpine);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sessions");
    }
  }, [stashId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  const sessions = spine?.sessions ?? [];

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-10 py-8">
          <div className="mb-5 border-b border-border pb-4">
            <h1 className="font-display text-[24px] font-bold tracking-tight text-foreground">
              Sessions
            </h1>
            <p className="mt-1.5 text-[12px] text-muted">
              {sessions.length} transcript{sessions.length === 1 ? "" : "s"}
              {stash ? <span> · in <span className="text-foreground">{stash.name}</span></span> : null}
            </p>
          </div>

          {error && (
            <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          {sessions.length > 0 ? (
            <div className="overflow-hidden rounded-lg border border-border bg-base">
              {sessions.map((session) => (
                <Link
                  key={session.session_id}
                  href={`/stashes/${stashId}/sessions/${encodeURIComponent(session.session_id)}`}
                  className="flex items-start gap-3 border-b border-border px-4 py-3 transition-colors last:border-b-0 hover:bg-raised"
                >
                  <span className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-[var(--color-brand-50)] text-[15px] text-[var(--color-brand-700)]">
                    💬
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-semibold text-foreground">
                      {session.title}
                    </span>
                    <span className="mt-1 block truncate text-[11.5px] text-muted">
                      {[
                        session.agent_name,
                        `${session.event_count} events`,
                        relativeTime(session.last_at),
                        formatBytes(session.size_bytes),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No sessions yet.
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}
