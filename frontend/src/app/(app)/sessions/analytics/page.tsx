"use client";

import { useEffect, useState } from "react";
import { SkeletonBlock } from "@/components/SkeletonStates";
import { getSessionsAnalytics, type SessionsAnalytics } from "@/lib/api";

/** Usage — an honest dashboard over the sessions the user can
 *  read (same scoping as the Sessions list): totals, sessions per day for the
 *  last 60 days, and breakdowns by agent and by person. Plain CSS bars, no
 *  chart library. */
export default function SessionAnalyticsPage() {
  const [data, setData] = useState<SessionsAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSessionsAnalytics()
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
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
          View stats about your session traces uploaded to Stash.
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
