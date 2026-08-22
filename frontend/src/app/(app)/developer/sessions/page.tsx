"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

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
  const router = useRouter();
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
        <div className="overflow-x-auto rounded border border-border bg-surface">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                <Th>Session</Th>
                <Th>User</Th>
                <Th>Agent</Th>
                <Th align="right">Events</Th>
                <Th align="right">Last</Th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr
                  key={s.session_id}
                  onClick={() => router.push(`/sessions/${encodeURIComponent(s.session_id)}`)}
                  className="cursor-pointer border-b border-border transition-colors last:border-b-0 hover:bg-raised"
                >
                  <td className="max-w-[360px] truncate px-4 py-3 text-[14px] text-foreground">
                    {s.title || s.session_id}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-[13.5px]">
                    {s.user_id ? (
                      <span className="text-foreground">{s.user_name}</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-[12px] text-muted-foreground">
                    {s.agent_name || "—"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-mono text-[12px] text-muted-foreground">
                    {s.event_count}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-mono text-[12px] text-muted-foreground">
                    {formatDate(s.last_event_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Th({
  children,
  align,
}: {
  children: React.ReactNode;
  align?: "right";
}) {
  return (
    <th
      className={`px-4 py-3 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </th>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
