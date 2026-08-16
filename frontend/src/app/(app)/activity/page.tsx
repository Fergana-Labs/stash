"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ActivityFeed from "@/components/ActivityFeed";
import SessionUploadsSection from "@/components/settings/SessionUploadsSection";
import { useAuth } from "@/hooks/useAuth";
import {
  listFileActivity,
  listMySessions,
  setSessionTeamMemory,
  type ActivityEvent,
  type SessionSummary,
} from "@/lib/api";

function relative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// The command center: exactly what has been uploaded, in detail, with the
// consent controls beside it. The trust surface of Multiplier.
export default function CommandCenterPage() {
  const { user, refresh } = useAuth();
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [events, setEvents] = useState<ActivityEvent[] | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    listMySessions(100)
      .then(setSessions)
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
    listFileActivity({ limit: 50 })
      .then((feed) => setEvents(feed.events))
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
  }, []);

  async function toggleTeamMemory(session: SessionSummary) {
    const next = !session.team_memory_excluded;
    try {
      const result = await setSessionTeamMemory(session.session_id, next);
      setNotice(
        next && result.pages_flagged > 0
          ? `Excluded. ${result.pages_flagged} team memory page${
              result.pages_flagged === 1 ? "" : "s"
            } built from this session will be rebuilt without it on the next curator run.`
          : ""
      );
      setSessions((prev) =>
        prev
          ? prev.map((s) =>
              s.session_id === session.session_id
                ? { ...s, team_memory_excluded: next }
                : s
            )
          : prev
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  }

  return (
    <main className="flex-1 overflow-y-auto px-4 py-10">
      <div className="w-full max-w-3xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Command center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Exactly what has been uploaded to your stash, and who can see it.
          </p>
        </div>

        {user && <SessionUploadsSection user={user} onUpdated={refresh} />}
        {error && <p className="text-xs text-error">{error}</p>}
        {notice && (
          <p className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-muted-foreground">
            {notice}
          </p>
        )}

        <section className="rounded-2xl border border-border bg-surface p-6">
          <h2 className="text-base font-semibold text-foreground">Uploaded transcripts</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Every session in your stash. Raw transcripts stay private; by
            default each session feeds your team&apos;s distilled wiki and
            skills — the toggle excludes one.
          </p>
          <div className="mt-4 divide-y divide-border">
            {sessions === null && (
              <p className="py-3 text-sm text-muted-foreground">Loading…</p>
            )}
            {sessions?.length === 0 && (
              <p className="py-3 text-sm text-muted-foreground">No sessions yet.</p>
            )}
            {sessions?.map((session) => (
              <div
                key={`${session.owner_user_id}-${session.session_id}`}
                className="flex items-center gap-3 py-2.5"
              >
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/sessions/${encodeURIComponent(session.session_id)}`}
                    className="block truncate text-sm text-foreground hover:underline"
                  >
                    {session.title}
                  </Link>
                  <p className="truncate text-xs text-muted-foreground">
                    {[
                      session.agent_name,
                      session.session_folder_name,
                      `${session.event_count} events`,
                      relative(session.last_event_at),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                {user && session.owner_user_id === user.id && session.id && (
                  <button
                    type="button"
                    onClick={() => toggleTeamMemory(session)}
                    className={`shrink-0 cursor-pointer rounded-md px-2 py-1 text-[11.5px] font-medium ${
                      session.team_memory_excluded
                        ? "bg-amber-600 text-white"
                        : "border border-border text-muted-foreground hover:text-foreground"
                    }`}
                    title={
                      session.team_memory_excluded
                        ? "Excluded from team learning — click to include"
                        : "Feeds team wiki & skills — click to exclude"
                    }
                  >
                    {session.team_memory_excluded ? "Excluded" : "In team memory"}
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-surface p-6">
          <h2 className="text-base font-semibold text-foreground">Files & pages</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Recent uploads and edits across your stash.
          </p>
          {events === null ? (
            <p className="mt-4 text-sm text-muted-foreground">Loading…</p>
          ) : events.length === 0 ? (
            <p className="mt-4 text-sm text-muted-foreground">No activity yet.</p>
          ) : (
            <ActivityFeed events={events} />
          )}
        </section>
      </div>
    </main>
  );
}
