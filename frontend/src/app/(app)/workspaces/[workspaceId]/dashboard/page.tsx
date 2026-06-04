"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { WorkspaceHomeSkeleton } from "../../../../../components/SkeletonStates";
import { useAuth } from "../../../../../hooks/useAuth";
import { listMySessions, type SessionSummary } from "../../../../../lib/api";

type Health = "On track" | "Watch" | "Blocked";
type EvidenceType = "Session" | "Slack" | "Gong";

interface Workstream {
  name: string;
  owner: string;
  status: Health;
  progress: number;
  focus: string;
  next: string;
}

interface Evidence {
  type: EvidenceType;
  title: string;
  source: string;
  time: string;
  owner: string;
  quote: string;
  sessionId?: string;
}

const SEEDED_SESSION_PREFIX = "webflow-mcp-";

const WORKSTREAMS: Workstream[] = [
  {
    name: "OAuth + workspace auth",
    owner: "Nadia",
    status: "On track",
    progress: 86,
    focus: "Finish scoped token exchange for Webflow sites and collections.",
    next: "Pair review on consent screen copy",
  },
  {
    name: "Designer context tools",
    owner: "Eli",
    status: "Watch",
    progress: 61,
    focus: "Expose selected element, style panel state, and page tree to MCP clients.",
    next: "Resolve iframe message contract",
  },
  {
    name: "CMS schema + publish actions",
    owner: "Maya",
    status: "On track",
    progress: 74,
    focus: "Add safe read/write tools for collections, fields, drafts, and publish jobs.",
    next: "Close validation cases for reference fields",
  },
  {
    name: "Sales engineering pilot",
    owner: "Sam",
    status: "Blocked",
    progress: 38,
    focus: "Validate agency workflows using fake customer calls and Slack asks.",
    next: "Get Webflow sandbox credentials",
  },
];

const RISKS = [
  {
    label: "Sandbox credentials",
    owner: "Sam",
    impact: "Pilot team cannot reproduce enterprise site permissions.",
  },
  {
    label: "Designer state drift",
    owner: "Eli",
    impact: "Agent reads can mismatch what the human is editing.",
  },
  {
    label: "Collection writes",
    owner: "Maya",
    impact: "Need stricter shape checks before write tools leave staging.",
  },
];

const SIGNALS = [
  { label: "Engineer sessions", value: "12", tone: "border-sky-200 bg-sky-50 text-sky-900" },
  { label: "Slack messages", value: "184", tone: "border-emerald-200 bg-emerald-50 text-emerald-900" },
  { label: "Gong calls", value: "8", tone: "border-amber-200 bg-amber-50 text-amber-900" },
  { label: "Open launch risks", value: "3", tone: "border-rose-200 bg-rose-50 text-rose-900" },
];

const EVIDENCE: Evidence[] = [
  {
    type: "Session",
    title: "OAuth handshake and site picker",
    source: "Codex transcript",
    time: "Jun 4, 9:20 AM",
    owner: "Nadia",
    quote: "Token exchange works locally; the remaining decision is where to persist per-site scopes.",
    sessionId: "webflow-mcp-auth-handshake",
  },
  {
    type: "Slack",
    title: "#webflow-mcp launch-room",
    source: "Slack",
    time: "Jun 4, 10:05 AM",
    owner: "Maya",
    quote: "If collection writes stay behind a dry-run preview, agencies will try this in production sooner.",
  },
  {
    type: "Gong",
    title: "Acme Sites agency pilot",
    source: "Gong sales call",
    time: "Jun 3, 2:30 PM",
    owner: "Sam",
    quote: "The buyer wants an agent that can audit CMS fields before a migration, not just generate pages.",
  },
  {
    type: "Session",
    title: "Designer iframe context bridge",
    source: "Claude transcript",
    time: "Jun 3, 4:15 PM",
    owner: "Eli",
    quote: "The bridge can emit selection changes; the unresolved part is debouncing page tree updates.",
    sessionId: "webflow-mcp-designer-context",
  },
  {
    type: "Gong",
    title: "Northstar Commerce discovery",
    source: "Gong sales call",
    time: "Jun 2, 11:00 AM",
    owner: "Aria",
    quote: "Their must-have is checking publish readiness across locales before Friday launches.",
  },
  {
    type: "Slack",
    title: "#solutions-eng triage",
    source: "Slack",
    time: "Jun 2, 4:45 PM",
    owner: "Nadia",
    quote: "Sales engineers need a one-screen explanation of what the MCP can read versus mutate.",
  },
];

const MILESTONES = [
  { date: "Jun 5", label: "Auth and site picker review", done: true },
  { date: "Jun 7", label: "Read-only tools dogfood", done: true },
  { date: "Jun 11", label: "CMS dry-run writes", done: false },
  { date: "Jun 14", label: "Agency pilot walkthrough", done: false },
];

function statusClass(status: Health): string {
  if (status === "On track") return "tag tag-success";
  if (status === "Watch") return "tag tag-warning";
  return "tag bg-rose-100 text-rose-700";
}

function evidenceClass(type: EvidenceType): string {
  if (type === "Session") return "tag tag-agent";
  if (type === "Slack") return "tag tag-human";
  return "tag border border-amber-200 bg-amber-50 text-amber-800";
}

function totalProgress(workstreams: Workstream[]): number {
  const total = workstreams.reduce((sum, item) => sum + item.progress, 0);
  return Math.round(total / workstreams.length);
}

function sessionTitle(session: SessionSummary): string {
  return session.title?.trim() || session.session_id;
}

export default function WebflowMcpDashboardPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading } = useAuth();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);

  useBreadcrumbs([{ label: "Dashboard" }], `${workspaceId}/dashboard`);

  const load = useCallback(async () => {
    const list = await listMySessions(workspaceId, 200);
    setSessions(list.filter((session) => session.session_id.startsWith(SEEDED_SESSION_PREFIX)));
  }, [workspaceId]);

  useEffect(() => {
    if (!user) return;
    load().catch(() => setSessions([]));
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const sessionIds = useMemo(
    () => new Set(sessions.map((session) => session.session_id)),
    [sessions],
  );
  const progress = totalProgress(WORKSTREAMS);
  const visibleSignals = SIGNALS.map((signal) => {
    if (signal.label !== "Engineer sessions") return signal;
    return { ...signal, value: String(Math.max(sessions.length, Number(signal.value))) };
  });

  if (loading) return <WorkspaceHomeSkeleton />;
  if (!user) return null;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto bg-base">
      <div className="mx-auto max-w-[1180px] px-8 py-7 lg:px-12">
        <header className="border-b border-border pb-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="sys-label">Project dashboard</div>
              <h1 className="mt-1 font-display text-[30px] font-bold leading-tight text-foreground">
                Webflow MCP Rollout
              </h1>
              <p className="mt-2 max-w-3xl text-[14px] leading-6 text-dim">
                Demo view for tracking engineering transcripts, Slack launch-room signals,
                and Gong sales-call evidence around adding MCP tools to Webflow.
              </p>
            </div>
            <div className="min-w-[190px] rounded-lg border border-border bg-surface px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="sys-label">Readiness</span>
                <span className="font-display text-[24px] font-bold text-foreground">{progress}%</span>
              </div>
              <div className="mt-3 h-2 rounded-full bg-raised">
                <div
                  className="h-2 rounded-full bg-emerald-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          </div>
        </header>

        <section className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {visibleSignals.map((signal) => (
            <div key={signal.label} className={`rounded-lg border px-4 py-3 ${signal.tone}`}>
              <div className="font-display text-[24px] font-bold leading-none">{signal.value}</div>
              <div className="mt-1 text-[12px] font-medium">{signal.label}</div>
            </div>
          ))}
        </section>

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.9fr)]">
          <section className="min-w-0">
            <div className="mb-2 flex items-center justify-between gap-3">
              <h2 className="font-display text-[18px] font-semibold text-foreground">Workstreams</h2>
              <span className="sys-label">4 owners</span>
            </div>
            <div className="overflow-hidden rounded-lg border border-border bg-base">
              {WORKSTREAMS.map((item) => (
                <div key={item.name} className="border-b border-border-subtle px-4 py-3 last:border-b-0">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-[14px] font-semibold text-foreground">{item.name}</h3>
                        <span className={statusClass(item.status)}>{item.status}</span>
                      </div>
                      <p className="mt-1 text-[13px] leading-5 text-dim">{item.focus}</p>
                    </div>
                    <div className="text-right text-[12px] text-muted">{item.owner}</div>
                  </div>
                  <div className="mt-3 flex items-center gap-3">
                    <div className="h-1.5 flex-1 rounded-full bg-raised">
                      <div
                        className="h-1.5 rounded-full bg-[var(--color-brand-500)]"
                        style={{ width: `${item.progress}%` }}
                      />
                    </div>
                    <span className="w-9 text-right text-[12px] font-medium text-dim">
                      {item.progress}%
                    </span>
                  </div>
                  <div className="mt-2 text-[12px] text-muted">Next: {item.next}</div>
                </div>
              ))}
            </div>
          </section>

          <aside className="min-w-0">
            <h2 className="mb-2 font-display text-[18px] font-semibold text-foreground">Milestones</h2>
            <div className="rounded-lg border border-border bg-surface px-4 py-3">
              {MILESTONES.map((item) => (
                <div key={item.label} className="flex gap-3 border-b border-border-subtle py-2 last:border-b-0">
                  <div
                    className={
                      "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] " +
                      (item.done
                        ? "border-emerald-500 bg-emerald-500 text-white"
                        : "border-border bg-base text-muted")
                    }
                  >
                    {item.done ? <span className="h-1.5 w-1.5 rounded-full bg-white" /> : null}
                  </div>
                  <div className="min-w-0">
                    <div className="text-[12px] font-medium text-muted">{item.date}</div>
                    <div className="text-[13px] leading-5 text-foreground">{item.label}</div>
                  </div>
                </div>
              ))}
            </div>

            <h2 className="mb-2 mt-5 font-display text-[18px] font-semibold text-foreground">Risks</h2>
            <div className="space-y-2">
              {RISKS.map((risk) => (
                <div key={risk.label} className="rounded-lg border border-border bg-base px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[13px] font-semibold text-foreground">{risk.label}</div>
                    <span className="sys-label">{risk.owner}</span>
                  </div>
                  <p className="mt-1 text-[12px] leading-5 text-dim">{risk.impact}</p>
                </div>
              ))}
            </div>
          </aside>
        </div>

        <section className="mt-7">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-[18px] font-semibold text-foreground">Evidence Feed</h2>
            <span className="sys-label">Sessions / Slack / Gong</span>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {EVIDENCE.map((item) => {
              const href =
                item.sessionId && sessionIds.has(item.sessionId)
                  ? `/workspaces/${workspaceId}/sessions/${item.sessionId}`
                  : null;
              return (
                <article key={`${item.type}-${item.title}`} className="rounded-lg border border-border bg-base p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={evidenceClass(item.type)}>{item.type}</span>
                    <span className="text-[12px] text-muted">{item.source}</span>
                    <span className="text-[12px] text-muted">-</span>
                    <span className="text-[12px] text-muted">{item.time}</span>
                  </div>
                  <h3 className="mt-2 text-[14px] font-semibold text-foreground">
                    {href ? (
                      <Link href={href} className="hover:text-[var(--color-brand-700)] hover:underline">
                        {item.title}
                      </Link>
                    ) : (
                      item.title
                    )}
                  </h3>
                  <p className="mt-1 text-[13px] leading-5 text-dim">{item.quote}</p>
                  <div className="mt-3 sys-label">{item.owner}</div>
                </article>
              );
            })}
          </div>
        </section>

        {sessions.length > 0 && (
          <section className="mt-7">
            <div className="mb-2 flex items-center justify-between gap-3">
              <h2 className="font-display text-[18px] font-semibold text-foreground">Seeded Transcripts</h2>
              <span className="sys-label">{sessions.length} live</span>
            </div>
            <div className="rounded-lg border border-border bg-surface">
              {sessions.slice(0, 8).map((session) => (
                <Link
                  key={session.session_id}
                  href={`/workspaces/${workspaceId}/sessions/${session.session_id}`}
                  className="flex items-center justify-between gap-3 border-b border-border-subtle px-4 py-2.5 text-[13px] last:border-b-0 hover:bg-raised"
                >
                  <span className="min-w-0 truncate text-foreground">{sessionTitle(session)}</span>
                  <span className="shrink-0 text-muted">
                    {session.event_count} events
                  </span>
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
