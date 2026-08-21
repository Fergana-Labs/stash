"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { PageHeading } from "@/components/developer/DocsPrimitives";
import { listDeveloperSessions, type DeveloperSession } from "@/lib/api";

export default function DeveloperSessions() {
  return (
    <DeveloperGate>
      <Sessions />
    </DeveloperGate>
  );
}

function Sessions() {
  const [sessions, setSessions] = useState<DeveloperSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listDeveloperSessions()
      .then((res) => setSessions(res.sessions))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load sessions"));
  }, []);

  return (
    <>
      <PageHeading title="Sessions">
        Every session your product has recorded, newest first, labelled by user. Rows with
        no user are the workspace&apos;s own agents — mostly the curator reading through
        what your users said.
      </PageHeading>
      {error ? (
        <p className="text-[15px] text-error">Couldn&apos;t load sessions: {error}</p>
      ) : sessions === null ? (
        <p className="text-[15px] text-muted-foreground">Loading…</p>
      ) : sessions.length === 0 ? (
        <p className="rounded border border-dashed border-border px-6 py-10 text-center text-[15px] leading-7 text-muted-foreground">
          No sessions yet. They appear as soon as your backend uploads one.
        </p>
      ) : (
        <div className="overflow-hidden rounded border border-border bg-surface">
          {sessions.map((s) => (
            <Link
              key={s.session_id}
              href={`/sessions/${encodeURIComponent(s.session_id)}`}
              className="flex items-center gap-4 border-b border-border px-5 py-3.5 transition-colors last:border-b-0 hover:bg-raised"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14.5px] text-foreground">
                  {s.title || s.session_id}
                </span>
                <span className="mt-0.5 block truncate font-mono text-[12px] text-muted-foreground">
                  {s.agent_name || "agent"} · {s.event_count} event
                  {s.event_count === 1 ? "" : "s"}
                </span>
              </span>
              {s.tenant_id ? (
                <span className="shrink-0 rounded-full bg-brand-500/10 px-2.5 py-0.5 text-[12px] font-medium text-brand-600">
                  {s.tenant_name}
                </span>
              ) : (
                <span className="shrink-0 rounded-full bg-raised px-2.5 py-0.5 text-[12px] text-dim">
                  {s.agent_name || "workspace"}
                </span>
              )}
              <span className="w-16 shrink-0 text-right font-mono text-[12px] text-muted-foreground">
                {formatDate(s.last_event_at)}
              </span>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
