"use client";

import { useEffect, useState, type ReactNode } from "react";
import { SkeletonBlock } from "@/components/SkeletonStates";
import CuratorLog from "@/components/memory/CuratorLog";
import WikiGraph from "@/components/memory/WikiGraph";
import EmbeddingSpaceExplorer from "@/components/viz/EmbeddingSpaceExplorer";
import {
  getEmbeddingProjection,
  getMemoryGraph,
  getSessionsAnalytics,
  type SessionsAnalytics,
  type WikiGraph as WikiGraphData,
} from "@/lib/api";
import type { EmbeddingProjection } from "@/lib/types";

/** Usage — an honest dashboard over the sessions the user can
 *  read (same scoping as the Sessions list): totals, sessions per day for the
 *  last 60 days, breakdowns by agent and by person, then the theme
 *  visualizations (session embedding map, memory wiki graph) and the
 *  curator log. Plain CSS bars for the stats, no chart library. Each
 *  visualization fetches independently so one slow endpoint can't hold the
 *  page. */
export default function SessionAnalyticsPage() {
  const [data, setData] = useState<SessionsAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [graph, setGraph] = useState<WikiGraphData | null>(null);
  const [graphLoaded, setGraphLoaded] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);
  const [projectionLoaded, setProjectionLoaded] = useState(false);
  const [projectionError, setProjectionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSessionsAnalytics()
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    getMemoryGraph()
      .then((g) => { if (!cancelled) setGraph(g); })
      .catch((reason) => { if (!cancelled) setGraphError(String(reason)); })
      .finally(() => { if (!cancelled) setGraphLoaded(true); });
    getEmbeddingProjection(2000, "sessions")
      .then((p) => { if (!cancelled) setProjection(p); })
      .catch((reason) => { if (!cancelled) setProjectionError(String(reason)); })
      .finally(() => { if (!cancelled) setProjectionLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center px-8">
        <p className="max-w-md text-center text-[13px] text-destructive">
          Couldn&apos;t load session analytics: {error}
        </p>
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-[1100px] px-8 pb-10 pt-7">
        <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
          Usage
        </h1>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          Stats and themes across the session traces uploaded to Stash.
        </p>

        <div className="mt-5 grid grid-cols-2 gap-4 sm:max-w-xs">
          <StatTile label="Sessions" value={data?.totals.sessions ?? null} />
          <StatTile label="Events" value={data?.totals.events ?? null} />
        </div>

        <section className="mt-5">
          <div className="sys-label mb-1.5">Sessions per day — last 60 days</div>
          <div className="card-soft p-4">
            {data ? <DayBars days={data.per_day} /> : <SkeletonBlock className="h-[120px] w-full" />}
          </div>
        </section>

        <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <BreakdownCard
            label="By agent"
            rows={data?.by_agent.map((r) => ({ name: r.agent, sessions: r.sessions })) ?? null}
            emptyText="No agent-run sessions yet."
          />
          <BreakdownCard
            label="By person"
            rows={data?.by_person ?? null}
            emptyText="No sessions yet."
          />
        </div>

        <section className="mt-5">
          <div className="sys-label mb-1.5">Session themes</div>
          <p className="mb-1.5 text-[12px] text-foreground/75">
            Each point is one session; nearby points began with similar user intent.
          </p>
          <div className="card-soft p-3">
            {!projectionLoaded ? (
              <SkeletonBlock className="h-[420px] w-full" />
            ) : projectionError ? (
              <VisualizationError message={projectionError} />
            ) : projection && projection.points.length > 0 ? (
              <div className="h-[420px]">
                <EmbeddingSpaceExplorer data={projection} />
              </div>
            ) : (
              <EmptyState>No session prompts have been embedded yet.</EmptyState>
            )}
          </div>
        </section>

        <section className="mt-5">
          <div className="sys-label mb-1.5">Memory wiki</div>
          <p className="mb-1.5 text-[12px] text-foreground/75">
            The curator&apos;s context graph — your wiki pages and the links between them.
            Click a node to open its page.
          </p>
          <div className="card-soft p-3">
            {!graphLoaded ? (
              <SkeletonBlock className="h-[560px] w-full" />
            ) : graphError ? (
              <VisualizationError message={graphError} />
            ) : graph && graph.nodes.length > 0 ? (
              <WikiGraph data={graph} />
            ) : (
              <EmptyState>
                No wiki pages yet. The Memory curator&apos;s nightly run compiles your
                history into a context graph of linked pages.
              </EmptyState>
            )}
          </div>
        </section>

        <div className="mt-5">
          <CuratorLog />
        </div>
      </div>
    </div>
  );
}

function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-[180px] items-center justify-center px-2 text-center text-[12.5px] text-foreground/75">
      {children}
    </div>
  );
}

function VisualizationError({ message }: { message: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center px-6 text-center">
      <div>
        <p className="text-[12.5px] font-medium text-destructive">
          Couldn&apos;t load this visualization.
        </p>
        <p className="mt-1 max-w-xl text-[11px] text-muted-foreground">{message}</p>
      </div>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: number | null }) {
  return (
    <section>
      <div className="sys-label mb-1.5">{label}</div>
      <div className="card-soft px-4 py-3">
        {value === null ? (
          <SkeletonBlock className="h-7 w-16" />
        ) : (
          <span className="font-display text-[24px] font-semibold tracking-tight text-foreground">
            {value.toLocaleString()}
          </span>
        )}
      </div>
    </section>
  );
}

function DayBars({ days }: { days: SessionsAnalytics["per_day"] }) {
  const max = Math.max(1, ...days.map((d) => d.sessions));
  const total = days.reduce((sum, d) => sum + d.sessions, 0);
  if (total === 0) {
    return (
      <div className="flex h-[120px] items-center justify-center text-[12.5px] text-muted-foreground">
        No sessions in the last 60 days.
      </div>
    );
  }
  return (
    <div>
      <div className="flex h-[120px] items-end gap-[2px]">
        {days.map((d) => (
          <div
            key={d.day}
            title={`${d.day}: ${d.sessions} session${d.sessions === 1 ? "" : "s"}`}
            className="min-w-0 flex-1 rounded-sm bg-brand-500/70"
            style={{ height: `${Math.max(d.sessions === 0 ? 0 : 4, (d.sessions / max) * 100)}%` }}
          />
        ))}
      </div>
      <div className="mt-1.5 flex justify-between font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
        <span>{days[0]?.day}</span>
        <span>{days[days.length - 1]?.day}</span>
      </div>
    </div>
  );
}

function BreakdownCard({
  label,
  rows,
  emptyText,
}: {
  label: string;
  rows: { name: string; sessions: number }[] | null;
  emptyText: string;
}) {
  const max = Math.max(1, ...(rows ?? []).map((r) => r.sessions));
  return (
    <section>
      <div className="sys-label mb-1.5">{label}</div>
      <div className="card-soft p-4">
        {rows === null ? (
          <SkeletonBlock className="h-[100px] w-full" />
        ) : rows.length === 0 ? (
          <div className="py-4 text-center text-[12.5px] text-muted-foreground">{emptyText}</div>
        ) : (
          <ul className="flex flex-col gap-2">
            {rows.map((r) => (
              <li key={r.name} className="flex items-center gap-3">
                <span className="w-40 min-w-0 truncate text-[13px] text-foreground">{r.name}</span>
                <span className="min-w-0 flex-1">
                  <span
                    className="block h-2 rounded-full bg-brand-500/60"
                    style={{ width: `${(r.sessions / max) * 100}%`, minWidth: 4 }}
                  />
                </span>
                <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                  {r.sessions.toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
