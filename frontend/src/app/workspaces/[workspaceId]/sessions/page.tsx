"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import SessionUpload from "../../../../components/SessionUpload";
import { SessionsIcon } from "../../../../components/StashIcons";
import { useAuth } from "../../../../hooks/useAuth";
import {
  listMySessions,
  type SessionSummary,
} from "../../../../lib/api";
import { groupSessionsByDayAndUser } from "../../../../lib/sessionGrouping";

export default function StashSessionsPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading } = useAuth();

  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const list = await listMySessions(workspaceId, 200);
      setSessions(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sessions");
    }
  }, [workspaceId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const filtered = useMemo(() => {
    if (!sessions) return null;
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => {
      const haystack = [s.agent_name, s.first_prompt_preview, s.session_id]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [sessions, query]);

  const grouped = useMemo(() => {
    if (!filtered) return null;
    return groupSessionsByDayAndUser(filtered);
  }, [filtered]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-12 py-8">
          <nav className="mb-4 flex flex-wrap items-center gap-1.5 text-[12.5px] text-muted">
            <Link href={`/workspaces/${workspaceId}`} className="hover:text-foreground">
              Home
            </Link>
            <span className="text-muted/60">/</span>
            <span className="font-medium text-foreground">Sessions</span>
          </nav>

          <div className="mb-1 flex h-10 w-10 items-center justify-center text-4xl text-muted">
            <SessionsIcon />
          </div>
          <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
            Sessions
          </h1>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          <div className="mt-5 mb-4 space-y-3">
            <SessionUpload workspaceId={workspaceId} onUploaded={load} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by agent, prompt, or session id…"
              className="w-full rounded-md border border-border bg-base px-3 py-1.5 text-[13px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-300)] focus:outline-none"
            />
          </div>

          {grouped && (
            <div className="space-y-7">
              {grouped.map((day) => (
                <section key={day.key}>
                  <div className="mb-2 flex items-center gap-3">
                    <h2 className="font-display text-[16px] font-semibold text-foreground">
                      {day.label}
                    </h2>
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
                      {day.count} session{day.count === 1 ? "" : "s"}
                    </span>
                  </div>
                  <div className="space-y-4">
                    {day.users.map((bucket) => (
                      <div key={`${day.key}:${bucket.user}`}>
                        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
                          {bucket.user}
                        </div>
                        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                          {bucket.sessions.map((s) => (
                            <Link
                              key={s.session_id}
                              href={`/workspaces/${workspaceId}/sessions/${encodeURIComponent(s.session_id)}`}
                              className="flex items-center gap-3 rounded-lg border border-border bg-base p-3 text-left transition-colors hover:border-[var(--color-brand-200)] hover:bg-[var(--color-brand-50)]"
                            >
                              <span className="flex h-7 w-7 items-center justify-center text-2xl text-muted">
                                <SessionsIcon />
                              </span>
                              <div className="min-w-0">
                                <div className="truncate text-[13.5px] font-semibold text-foreground">
                                  {sessionTitle(s)}
                                </div>
                                <div className="truncate text-[11.5px] text-muted">
                                  {sessionSubtitle(s)}
                                </div>
                              </div>
                            </Link>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
              {filtered?.length === 0 && (
                <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted">
                  {sessions && sessions.length === 0
                    ? "No sessions yet."
                    : "No sessions match your search."}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
  );
}

function sessionTitle(s: SessionSummary): string {
  if (s.agent_name) return s.agent_name;
  const id = s.session_id;
  const short = id.replace(/^session[-_]/, "").slice(0, 8);
  return short || id;
}

function sessionSubtitle(s: SessionSummary): string {
  const preview = (s.first_prompt_preview || "").trim().replace(/\s+/g, " ");
  const truncated = preview.length > 80 ? preview.slice(0, 80) + "…" : preview;
  const when = formatRelative(s.last_event_at);
  if (truncated && when) return `${truncated} · ${when}`;
  return truncated || when || `${s.event_count} events`;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return new Date(iso).toLocaleDateString();
}
