import type { Metadata } from "next";

import AnalyticsClient, {
  type AnalyticsPayload,
  type CohortResponse,
} from "./AnalyticsClient";

export const metadata: Metadata = {
  title: "Analytics · Admin",
  robots: { index: false, follow: false },
};

const VALID_BUCKETS = ["month", "week", "rolling_7d"] as const;
const VALID_MODES = ["standard", "future"] as const;
const VALID_FILTERS = ["all", "active"] as const;
const VALID_PATHS = ["migrant", "memory", "sharing"] as const;

type SearchParams = { [key: string]: string | string[] | undefined };

function readParam<T extends string>(
  raw: string | string[] | undefined,
  allowed: readonly T[],
  fallback: T,
): T {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return (allowed as readonly string[]).includes(v ?? "") ? (v as T) : fallback;
}

function readOptionalParam<T extends string>(
  raw: string | string[] | undefined,
  allowed: readonly T[],
): T | undefined {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return v && (allowed as readonly string[]).includes(v) ? (v as T) : undefined;
}

async function fetchJSON<T>(url: string, token: string): Promise<T | string> {
  const res = await fetch(url, {
    headers: { "X-Admin-Token": token },
    cache: "no-store",
  });
  if (!res.ok) return await res.text();
  return (await res.json()) as T;
}

export default async function AnalyticsAdminPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const bucket = readParam(sp.bucket, VALID_BUCKETS, "month");
  const mode = readParam(sp.mode, VALID_MODES, "standard");
  const eventsFilter = readParam(sp.events_filter, VALID_FILTERS, "all");
  const funnelPath = readOptionalParam(sp.path, VALID_PATHS);
  const windowDays = Math.min(
    180,
    Math.max(1, Number((Array.isArray(sp.days) ? sp.days[0] : sp.days) ?? 30)),
  );

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";
  const token = process.env.ADMIN_PASSWORD;
  if (!token) {
    return (
      <ErrorShell
        title="Admin not configured"
        body="ADMIN_PASSWORD env var is not set on the www server."
      />
    );
  }

  const fmt = (path: string, qs: Record<string, string | number | undefined>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(qs)) {
      if (v !== undefined && v !== "") q.set(k, String(v));
    }
    return `${apiUrl}${path}${q.toString() ? `?${q.toString()}` : ""}`;
  };

  // All four payloads + cohorts fetched in parallel — same admin secret on
  // every request, single network round-trip from the user's perspective.
  const [contentActivity, summary, funnel, pathMix, surfaceMix, topEvents, cohorts] =
    await Promise.all([
      fetchJSON(
        fmt("/api/v1/admin/analytics/content-activity", { days: windowDays }),
        token,
      ),
      fetchJSON(fmt("/api/v1/admin/analytics/summary", { days: 7 }), token),
      fetchJSON(
        fmt("/api/v1/admin/analytics/onboarding-funnel", {
          days: windowDays,
          path: funnelPath,
        }),
        token,
      ),
      fetchJSON(
        fmt("/api/v1/admin/analytics/path-mix", {
          days: windowDays,
          bucket: "day",
        }),
        token,
      ),
      fetchJSON(
        fmt("/api/v1/admin/analytics/surface-mix", {
          days: windowDays,
          bucket: "day",
        }),
        token,
      ),
      fetchJSON(
        fmt("/api/v1/admin/analytics/top-events", {
          days: windowDays,
          limit: 20,
        }),
        token,
      ),
      fetchJSON<CohortResponse>(
        fmt("/api/v1/admin/cohorts/engagement", {
          bucket,
          mode,
          events_filter: eventsFilter,
        }),
        token,
      ),
    ]);

  for (const [name, v] of [
    ["content-activity", contentActivity],
    ["summary", summary],
    ["onboarding-funnel", funnel],
    ["path-mix", pathMix],
    ["surface-mix", surfaceMix],
    ["top-events", topEvents],
    ["cohorts", cohorts],
  ] as const) {
    if (typeof v === "string") {
      return <ErrorShell title={`Backend error · ${name}`} body={v} />;
    }
  }

  const payload: AnalyticsPayload = {
    contentActivity: contentActivity as AnalyticsPayload["contentActivity"],
    summary: summary as AnalyticsPayload["summary"],
    funnel: funnel as AnalyticsPayload["funnel"],
    pathMix: pathMix as AnalyticsPayload["pathMix"],
    surfaceMix: surfaceMix as AnalyticsPayload["surfaceMix"],
    topEvents: topEvents as AnalyticsPayload["topEvents"],
    cohorts: cohorts as CohortResponse,
  };

  return (
    <AnalyticsClient
      data={payload}
      bucket={bucket}
      mode={mode}
      eventsFilter={eventsFilter}
      funnelPath={funnelPath ?? "all"}
      windowDays={windowDays}
    />
  );
}

function ErrorShell({ title, body }: { title: string; body: string }) {
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-[720px] px-7 py-20">
        <h1 className="text-2xl font-semibold text-gray-800">{title}</h1>
        <pre className="mt-4 whitespace-pre-wrap rounded-md border border-gray-200 bg-white p-4 font-mono text-[12px] text-gray-600">
          {body}
        </pre>
      </div>
    </main>
  );
}
