"use client";

import { useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import { useShareModal } from "../../lib/shareModalContext";
import {
  listMySessions,
  materializeSession,
  type SessionSummary,
} from "../../lib/api";

export default function HistoryPage() {
  const { user, loading, logout } = useAuth();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(true);

  useEffect(() => {
    if (!user) return;
    listMySessions()
      .then(setSessions)
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoadingSessions(false));
  }, [user]);

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <main className="mx-auto max-w-[1100px] px-7 py-12">
        <h1 className="font-display text-[32px] font-bold tracking-[-0.02em] text-foreground">
          History
        </h1>
        <p className="mt-2 text-[14px] text-dim">
          Recent agent sessions across your workspaces. Share any session to send a colleague a link.
        </p>

        {loadError && <p className="mt-6 text-[13px] text-red-500">{loadError}</p>}
        {loadingSessions && !loadError && (
          <p className="mt-6 text-[13px] text-muted">Loading sessions…</p>
        )}

        {!loadingSessions && sessions.length === 0 && !loadError && (
          <p className="mt-12 text-center text-[14px] text-muted">
            No sessions yet. Run an agent against this workspace and they&apos;ll appear here.
          </p>
        )}

        <ul className="mt-6 divide-y divide-border-subtle border-y border-border-subtle">
          {sessions.map((s) => (
            <SessionRow key={s.session_id} session={s} />
          ))}
        </ul>
      </main>
    </AppShell>
  );
}

function SessionRow({ session }: { session: SessionSummary }) {
  return (
    <li className="flex items-start justify-between gap-4 py-4">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-wider text-muted">
            {session.agent_name || "agent"}
          </span>
          <span className="text-[12px] text-dim">{session.event_count} events</span>
          <span className="text-[12px] text-dim">{relativeTime(session.last_event_at)}</span>
          {session.workspace_name && (
            <span className="text-[12px] text-dim">in {session.workspace_name}</span>
          )}
        </div>
        {session.first_prompt_preview && (
          <p className="mt-1 line-clamp-2 text-[14px] text-foreground">
            {session.first_prompt_preview}
          </p>
        )}
        <p className="mt-1 font-mono text-[10px] text-muted">{session.session_id.slice(0, 12)}…</p>
      </div>
      <SessionActions session={session} />
    </li>
  );
}

function SessionActions({ session }: { session: SessionSummary }) {
  const shareModal = useShareModal();
  const [working, setWorking] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onShare = async () => {
    if (!session.workspace_id) {
      setErr("Session is missing a workspace");
      return;
    }
    setWorking(true);
    setErr(null);
    try {
      const result = await materializeSession(session.workspace_id, session.session_id);
      shareModal.open({
        stashId: session.workspace_id,
        stashName: session.workspace_name ?? undefined,
        initial: [
          {
            object_type: "page",
            object_id: result.page.id,
            label_override: `Session ${session.session_id.slice(0, 8)}`,
          },
        ],
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to share");
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="flex shrink-0 items-center gap-2">
      <button
        onClick={onShare}
        disabled={working}
        className="rounded border border-border bg-raised px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-foreground hover:border-foreground disabled:opacity-50"
      >
        {working ? "Preparing…" : "Share"}
      </button>
      {err && <span className="text-[11px] text-red-500">{err}</span>}
    </div>
  );
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 30) return `${d}d ago`;
  return `${Math.round(d / 30)}mo ago`;
}
