"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

export type Cohort = {
  cohort_label: string;
  cohort_start: string;
  size: number;
  retention: number[];
  active_users: number[];
  avg_cumulative_actions: number[];
};

export type CohortResponse = {
  bucket: "month" | "week" | "rolling_7d";
  mode: "standard" | "future";
  max_period: number;
  user_type: string;
  cohorts: Cohort[];
  totals: { users: number; events: number };
  generated_at: string;
};

const BUCKET_OPTS = [
  { v: "month", label: "Month" },
  { v: "week", label: "Week" },
  { v: "rolling_7d", label: "Rolling 7-day" },
] as const;

const MODE_OPTS = [
  { v: "standard", label: "Standard" },
  { v: "future", label: "Future" },
] as const;

function periodHeader(bucket: CohortResponse["bucket"], p: number): string {
  if (bucket === "month") return `M${p}`;
  if (bucket === "week") return `W${p}`;
  return p === 0 ? "D0–6" : `D${p * 7}–${p * 7 + 6}`;
}

function periodOneLabel(bucket: CohortResponse["bucket"]): string {
  if (bucket === "month") return "M1 retention";
  if (bucket === "week") return "W1 retention";
  return "Day 7 retention";
}

function retentionColor(r: number): string {
  if (r <= 0) return "transparent";
  // Light → dark green ramp.
  const alpha = Math.min(1, 0.08 + r * 0.85);
  return `rgba(34, 197, 94, ${alpha.toFixed(3)})`;
}

export default function CohortClient({
  data,
  bucket,
  mode,
}: {
  data: CohortResponse;
  bucket: CohortResponse["bucket"];
  mode: CohortResponse["mode"];
}) {
  const router = useRouter();
  const params = useSearchParams();

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    router.push(`/admin/cohorts?${next.toString()}`);
  };

  const periods = data.cohorts[0]?.retention.length ?? 0;
  const periodIndices = Array.from({ length: periods }, (_, i) => i);

  // Weighted period-1 retention across all cohorts that have a period 1.
  const eligible = data.cohorts.filter((c) => c.retention.length > 1 && c.size > 0);
  const totalUsers = eligible.reduce((s, c) => s + c.size, 0);
  const weightedP1 =
    totalUsers > 0
      ? eligible.reduce((s, c) => s + c.retention[1] * c.size, 0) / totalUsers
      : 0;

  const maxCohortSize = Math.max(1, ...data.cohorts.map((c) => c.size));

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border-subtle">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-7">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="font-display text-[20px] font-black tracking-[-0.03em] text-ink"
            >
              stash
            </Link>
            <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
              Admin · Engagement cohorts
            </span>
          </div>
          <span className="font-mono text-[11px] text-muted">
            generated {new Date(data.generated_at).toLocaleString()}
          </span>
        </div>
      </header>

      <section className="mx-auto max-w-[1400px] px-7 py-10">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <h1 className="font-display text-[36px] font-black leading-[1.05] tracking-[-0.03em] text-ink">
              Engagement cohorts
            </h1>
            <p className="mt-2 max-w-[560px] text-[14px] leading-[1.55] text-dim">
              Users grouped by their first activity bucket. Each cell is the
              fraction of that cohort active in the corresponding period.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Toggle
              label="Bucket"
              value={bucket}
              options={BUCKET_OPTS}
              onChange={(v) => setParam("bucket", v)}
            />
            <Toggle
              label="Mode"
              value={mode}
              options={MODE_OPTS}
              onChange={(v) => setParam("mode", v)}
            />
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat label="Total users" value={data.totals.users.toLocaleString()} />
          <Stat label="Total events" value={data.totals.events.toLocaleString()} />
          <Stat
            label={periodOneLabel(bucket)}
            value={`${(weightedP1 * 100).toFixed(1)}%`}
          />
        </div>

        <div className="mt-10">
          <h2 className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            Cohort sizes
          </h2>
          <div className="space-y-1.5">
            {data.cohorts.map((c) => (
              <div key={c.cohort_label} className="flex items-center gap-3">
                <span className="w-24 shrink-0 font-mono text-[11px] text-dim">
                  {c.cohort_label}
                </span>
                <div className="relative h-5 flex-1 overflow-hidden rounded-sm bg-background">
                  <div
                    className="h-full bg-brand/70"
                    style={{ width: `${(c.size / maxCohortSize) * 100}%` }}
                  />
                </div>
                <span className="w-12 shrink-0 text-right font-mono text-[11px] text-ink">
                  {c.size}
                </span>
              </div>
            ))}
            {data.cohorts.length === 0 && (
              <p className="text-[13px] text-dim">No cohorts to display.</p>
            )}
          </div>
        </div>

        <div className="mt-10 overflow-x-auto">
          <h2 className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            Retention heatmap · {mode === "standard" ? "standard" : "future"}
          </h2>
          <table className="border-collapse font-mono text-[11px]">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-background px-3 py-2 text-left text-muted">
                  Cohort
                </th>
                <th className="px-3 py-2 text-right text-muted">Size</th>
                {periodIndices.map((p) => (
                  <th
                    key={p}
                    className="px-3 py-2 text-right text-muted"
                  >
                    {periodHeader(bucket, p)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.cohorts.map((c) => (
                <tr key={c.cohort_label} className="border-t border-border-subtle">
                  <td className="sticky left-0 z-10 bg-background px-3 py-1.5 text-dim">
                    {c.cohort_label}
                  </td>
                  <td className="px-3 py-1.5 text-right text-ink">{c.size}</td>
                  {c.retention.map((r, p) => (
                    <td
                      key={p}
                      className="px-3 py-1.5 text-right text-ink"
                      style={{ backgroundColor: retentionColor(r) }}
                      title={`${c.active_users[p]} of ${c.size} active`}
                    >
                      {r > 0 ? `${(r * 100).toFixed(0)}%` : "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border-subtle p-4">
      <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
        {label}
      </p>
      <p className="mt-2 font-display text-[24px] font-black tracking-[-0.02em] text-ink">
        {value}
      </p>
    </div>
  );
}

function Toggle<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly { v: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div>
      <p className="mb-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-muted">
        {label}
      </p>
      <div className="inline-flex overflow-hidden rounded-md border border-border-subtle">
        {options.map((opt) => {
          const active = opt.v === value;
          return (
            <button
              key={opt.v}
              type="button"
              onClick={() => onChange(opt.v)}
              className={
                "px-3 py-1.5 text-[12px] transition " +
                (active
                  ? "bg-ink text-background"
                  : "bg-background text-dim hover:text-ink")
              }
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
