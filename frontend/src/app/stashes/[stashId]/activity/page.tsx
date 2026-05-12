"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../../../components/AppShell";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import { FileIcon, PageIcon, PersonIcon, SessionsIcon } from "../../../../components/StashIcons";
import { useAuth } from "../../../../hooks/useAuth";
import { listStashActivity, getWorkspace, type ActivityEvent } from "../../../../lib/api";
import type { Workspace } from "../../../../lib/types";

const VERB: Record<string, string> = {
  "session.uploaded": "pushed a transcript",
  "page.updated": "edited a page",
  "file.uploaded": "uploaded a file",
  "member.joined": "joined the stash",
};

const PALETTE = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];

function colorFor(name: string) {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

function targetHref(stashId: string, ev: ActivityEvent): string | null {
  if (ev.kind === "session.uploaded") return `/stashes/${stashId}/sessions/${encodeURIComponent(ev.target_id)}`;
  if (ev.kind === "page.updated") return `/stashes/${stashId}/p/${ev.target_id}`;
  if (ev.kind === "file.uploaded") return `/stashes/${stashId}/f/${ev.target_id}`;
  return null;
}

function relative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function EventIcon({ kind }: { kind: string }) {
  if (kind === "session.uploaded") return <SessionsIcon />;
  if (kind === "page.updated") return <PageIcon />;
  if (kind === "file.uploaded") return <FileIcon />;
  if (kind === "member.joined") return <PersonIcon />;
  return null;
}

export default function ActivityPage() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const { user, loading, logout } = useAuth();
  const [stash, setStash] = useState<Workspace | null>(null);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [fetching, setFetching] = useState(true);

  useBreadcrumbs([{ label: "Activity" }], `${stashId}/activity`);

  const load = useCallback(async () => {
    setFetching(true);
    try {
      setStash(await getWorkspace(stashId));
      setEvents(await listStashActivity(stashId, 100));
    } catch {
      /* empty */
    }
    setFetching(false);
  }, [stashId]);

  useEffect(() => { if (user) load(); }, [user, load]);
  useEffect(() => { if (!loading && !user) router.push("/login"); }, [user, loading, router]);

  if (loading) return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="mx-auto max-w-3xl px-12 py-10">
        <h1 className="font-display text-[30px] font-bold tracking-tight text-foreground">
          Activity
        </h1>
        <p className="mt-1 text-[13px] text-muted">
          Recent changes in {stash?.name || "this stash"}.
        </p>

        {fetching ? (
          <p className="mt-8 text-[13px] text-muted">Loading…</p>
        ) : events.length === 0 ? (
          <p className="mt-8 text-[13px] text-muted">
            No activity yet. Push a transcript, edit a page, or upload a file.
          </p>
        ) : (
          <div className="mt-6 flex flex-col">
            {events.map((ev, i) => {
              const name = ev.actor.display_name || ev.actor.name;
              const c = colorFor(name);
              const href = targetHref(stashId, ev);
              return (
                <div
                  key={`${ev.kind}-${ev.target_id}-${i}`}
                  className="flex items-start gap-3 border-b border-border py-3 last:border-b-0"
                >
                  <span
                    className={
                      "inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-semibold " +
                      c.bg + " " + c.fg
                    }
                  >
                    {name.slice(0, 2).toUpperCase()}
                  </span>
                  <div className="min-w-0 flex-1 text-[13px]">
                    <span className="font-medium text-foreground">{name}</span>{" "}
                    <span className="text-muted">{VERB[ev.kind] || ev.kind}</span>
                    {ev.target_label && href && (
                      <>
                        {" "}
                        <Link href={href} className="font-medium text-foreground hover:text-[var(--color-brand-700)]">
                          <span className="inline-flex items-center gap-1">
                            <span className="inline-flex text-[15px] text-muted">
                              <EventIcon kind={ev.kind} />
                            </span>
                            {ev.target_label}
                          </span>
                        </Link>
                      </>
                    )}
                    {ev.target_label && !href && (
                      <> <span className="text-foreground">{ev.target_label}</span></>
                    )}
                    <div className="mt-0.5 text-[11px] text-muted">{relative(ev.ts)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
}
