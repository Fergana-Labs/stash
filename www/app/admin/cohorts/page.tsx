import type { Metadata } from "next";

import CohortClient, { type CohortResponse } from "./CohortClient";

export const metadata: Metadata = {
  title: "Engagement cohorts · Admin",
  robots: { index: false, follow: false },
};

const VALID_BUCKETS = ["month", "week", "rolling_7d"] as const;
const VALID_MODES = ["standard", "future"] as const;
const VALID_FILTERS = ["all", "active"] as const;

type SearchParams = { [key: string]: string | string[] | undefined };

function readParam<T extends string>(
  raw: string | string[] | undefined,
  allowed: readonly T[],
  fallback: T,
): T {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return (allowed as readonly string[]).includes(v ?? "") ? (v as T) : fallback;
}

export default async function CohortsAdminPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const bucket = readParam(sp.bucket, VALID_BUCKETS, "month");
  const mode = readParam(sp.mode, VALID_MODES, "standard");
  const eventsFilter = readParam(sp.events_filter, VALID_FILTERS, "all");

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

  const url = `${apiUrl}/api/v1/admin/cohorts/engagement?bucket=${bucket}&mode=${mode}&events_filter=${eventsFilter}`;
  const res = await fetch(url, {
    headers: { "X-Admin-Token": token },
    cache: "no-store",
  });

  if (!res.ok) {
    return (
      <ErrorShell
        title={`Backend error · ${res.status}`}
        body={await res.text()}
      />
    );
  }

  const data = (await res.json()) as CohortResponse;
  return (
    <CohortClient
      data={data}
      bucket={bucket}
      mode={mode}
      eventsFilter={eventsFilter}
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
