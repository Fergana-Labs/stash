"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../../../../components/AppShell";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../../hooks/useAuth";
import {
  downloadStashTranscriptText,
  getStashTranscript,
  getWorkspace,
  type SessionTranscript,
} from "../../../../../lib/api";
import type { Workspace } from "../../../../../lib/types";

interface MessageTurn {
  kind: "message";
  who: string; // "user" / "assistant" / etc.
  role?: string;
  name: string;
  time?: string;
  content: string;
}
interface DateTurn {
  kind: "date";
  date: string;
  isNew?: boolean;
}
interface SummaryTurn {
  kind: "summary";
  content: string;
}
type Turn = MessageTurn | DateTurn | SummaryTurn;

function parseJsonl(text: string): Turn[] {
  const out: Turn[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    let obj: Record<string, unknown>;
    try {
      obj = JSON.parse(line) as Record<string, unknown>;
    } catch {
      out.push({ kind: "message", who: "user", name: "user", content: line });
      continue;
    }
    const t = (obj.type as string) || "user";
    if (t === "summary") {
      out.push({ kind: "summary", content: (obj.summary as string) || "" });
    } else if (t === "date") {
      const date = (obj.date as string) || "";
      out.push({ kind: "date", date, isNew: /new messages/i.test(date) });
    } else {
      out.push({
        kind: "message",
        who: t,
        role: obj.role as string | undefined,
        name: (obj.name as string) || (t === "assistant" ? "agent" : "user"),
        time: obj.time as string | undefined,
        content: (obj.content as string) || (obj.text as string) || "",
      });
    }
  }
  return out;
}

const AVATAR_PALETTE: { bg: string; fg: string }[] = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];

function avatarFor(name: string) {
  // Deterministic color per author (no hardcoded names). djb2-ish hash.
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

export default function SessionViewerPage() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const sessionId = decodeURIComponent(params.sessionId as string);
  const { user, loading, logout } = useAuth();

  const [stash, setStash] = useState<Workspace | null>(null);
  const [transcript, setTranscript] = useState<SessionTranscript | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState("");

  useBreadcrumbs(
    [{ label: "Sessions" }, { label: `#${sessionId}` }],
    `${stashId}/session/${sessionId}`
  );

  const load = useCallback(async () => {
    try {
      setStash(await getWorkspace(stashId));
      const tx = await getStashTranscript(stashId, sessionId);
      setTranscript(tx);
      const text = await downloadStashTranscriptText(stashId, sessionId);
      setTurns(parseJsonl(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load session");
    }
  }, [stashId, sessionId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  const summary = turns.find((t): t is SummaryTurn => t.kind === "summary");
  const messageTurns = turns.filter((t) => t.kind !== "summary");

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-12 py-8">
          {/* Title row — chat-style header (matches mockup chat-customer-discovery) */}
          <div className="mb-5 flex items-start justify-between gap-4 border-b border-border pb-4">
            <div className="min-w-0">
              <h1 className="font-display text-[24px] font-bold tracking-tight text-foreground">
                #{sessionId.replace(/^acme-/, "")}
              </h1>
              {summary && (
                <p className="mt-1 text-[13px] text-muted">{summary.content}</p>
              )}
              {transcript && (
                <p className="mt-1.5 text-[11.5px] text-muted">
                  {messageTurns.filter((t) => t.kind === "message").length} messages
                  {stash ? <span> · in <span className="text-foreground">{stash.name}</span></span> : null}
                </p>
              )}
            </div>
            {transcript?.agent_name && (
              <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-base px-2 py-1 text-[11px] text-foreground">
                <span className="font-mono">⌘</span> {transcript.agent_name}
              </span>
            )}
          </div>

          {error && (
            <div className="mb-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          <div className="flex flex-col">
            {messageTurns.map((turn, i) =>
              turn.kind === "date" ? (
                <DateDivider key={i} date={turn.date} isNew={turn.isNew} />
              ) : turn.kind === "message" ? (
                <MessageRow key={i} turn={turn} />
              ) : null
            )}
            {!error && messageTurns.length === 0 && (
              <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted">
                Loading transcript…
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function DateDivider({ date, isNew }: { date: string; isNew?: boolean }) {
  return (
    <div className="my-3 flex items-center gap-2">
      <div className="h-px flex-1 bg-border" />
      <span
        className={
          "rounded-full px-2 py-0.5 text-[10.5px] font-medium uppercase tracking-wide " +
          (isNew
            ? "bg-[var(--color-brand-100)] text-[var(--color-brand-800)]"
            : "bg-surface text-muted ring-1 ring-border")
        }
      >
        {date}
      </span>
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}

function MessageRow({ turn }: { turn: MessageTurn }) {
  const isAgent = turn.who === "assistant" || /agent/i.test(turn.name);
  const avatar = avatarFor(turn.name);
  return (
    <div className="msg-row group flex gap-3 rounded-md px-2 py-2">
      <span
        className={
          "inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-semibold " +
          avatar.bg +
          " " +
          avatar.fg
        }
      >
        {initials(turn.name)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2 text-[12.5px]">
          <span className="font-semibold text-foreground">{turn.name}</span>
          {isAgent && (
            <span className="rounded bg-[var(--color-brand-50)] px-1 py-0 text-[9.5px] uppercase tracking-wide text-[var(--color-brand-700)] ring-1 ring-[var(--color-brand-200)]">
              app
            </span>
          )}
          {turn.role === "guest" && (
            <span className="rounded bg-indigo-50 px-1 py-0 text-[9.5px] uppercase tracking-wide text-indigo-700 ring-1 ring-indigo-200">
              guest
            </span>
          )}
          {turn.time && <span className="text-[10.5px] text-muted">{turn.time}</span>}
        </div>
        <div className="mt-0.5 whitespace-pre-wrap text-[13.5px] leading-relaxed text-foreground">
          {turn.content}
        </div>
      </div>
    </div>
  );
}
