import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import type { CatalogCard } from "@/lib/discover";

import { updateDiscoverWorkspace } from "./actions";

export const metadata: Metadata = {
  title: "Discover curation - Admin",
  robots: { index: false, follow: false },
};

type SearchParams = { [key: string]: string | string[] | undefined };
type Status = "all" | "curated" | "uncurated";

function readParam(raw: string | string[] | undefined): string {
  return Array.isArray(raw) ? (raw[0] ?? "") : (raw ?? "");
}

function readStatus(raw: string | string[] | undefined): Status {
  const value = readParam(raw);
  return value === "curated" || value === "uncurated" ? value : "all";
}

export default async function DiscoverAdminPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const status = readStatus(sp.status);
  const q = readParam(sp.q).slice(0, 128);

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

  const qs = new URLSearchParams({ status, limit: "150" });
  if (q) qs.set("q", q);
  const res = await fetch(`${apiUrl}/api/v1/admin/discover/workspaces?${qs}`, {
    headers: { "X-Admin-Token": token },
    cache: "no-store",
  });

  if (!res.ok) {
    return (
      <ErrorShell
        title={`Backend error - ${res.status}`}
        body={await res.text()}
      />
    );
  }

  const data = (await res.json()) as { workspaces: CatalogCard[] };
  const curatedCount = data.workspaces.filter((w) => w.discoverable).length;

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-[1100px] px-7 py-10">
        <header className="flex flex-col gap-5 border-b border-border-subtle pb-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
              Admin
            </p>
            <h1 className="mt-2 font-display text-[34px] font-black tracking-[-0.03em] text-ink">
              Discover curation
            </h1>
            <p className="mt-2 max-w-[600px] text-[14px] leading-[1.6] text-dim">
              Choose which public Stashes are listed on the Discover page.
            </p>
          </div>
          <div className="flex gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
            <Metric label="Visible" value={curatedCount} />
            <Metric label="Loaded" value={data.workspaces.length} />
          </div>
        </header>

        <section className="mt-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-2">
            {(["all", "curated", "uncurated"] as const).map((s) => (
              <Link
                key={s}
                href={`/admin/discover?status=${s}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
                className={
                  "rounded-md px-3 py-2 text-[13px] transition " +
                  (status === s
                    ? "bg-raised font-medium text-ink"
                    : "text-dim hover:bg-raised hover:text-ink")
                }
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </Link>
            ))}
          </div>

          <form action="/admin/discover" className="flex w-full gap-2 md:max-w-[420px]">
            <input type="hidden" name="status" value={status} />
            <input
              name="q"
              defaultValue={q}
              placeholder="Search public stashes"
              className="min-w-0 flex-1 rounded-md border border-border-subtle bg-background px-3 py-2 text-[14px] text-ink outline-none transition placeholder:text-muted focus:border-brand"
            />
            <button
              type="submit"
              className="rounded-md bg-ink px-4 py-2 text-[14px] font-medium text-background transition hover:opacity-90"
            >
              Search
            </button>
          </form>
        </section>

        <section className="mt-6 overflow-hidden rounded-lg border border-border-subtle">
          {data.workspaces.length === 0 ? (
            <div className="bg-surface px-5 py-12 text-center text-[14px] text-muted">
              No public Stashes match this view.
            </div>
          ) : (
            <div className="divide-y divide-border-subtle">
              {data.workspaces.map((workspace) => (
                <WorkspaceRow key={workspace.id} workspace={workspace} />
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function WorkspaceRow({ workspace }: { workspace: CatalogCard }) {
  const owner = workspace.creator_display_name || workspace.creator_name;
  return (
    <div className="grid gap-4 bg-surface px-5 py-4 md:grid-cols-[1fr_auto] md:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="truncate font-display text-[17px] font-bold text-ink">
            {workspace.name}
          </h2>
          {workspace.discoverable ? <Badge tone="green">Listed</Badge> : <Badge>Unlisted</Badge>}
          {workspace.featured ? <Badge tone="orange">Featured</Badge> : null}
        </div>
        <p className="mt-1 line-clamp-2 max-w-[720px] text-[13px] leading-[1.5] text-dim">
          {workspace.summary || workspace.description || "No description yet."}
        </p>
        <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.1em] text-muted">
          by {owner} / {workspace.page_count} pages / {workspace.table_count} tables /{" "}
          {workspace.file_count} files
        </p>
      </div>

      <form action={updateDiscoverWorkspace} className="flex flex-wrap gap-2 md:justify-end">
        <input type="hidden" name="workspace_id" value={workspace.id} />
        {workspace.discoverable ? (
          <button
            type="submit"
            name="action"
            value="unlist"
            className="rounded-md border border-border-subtle px-3 py-2 text-[13px] text-dim transition hover:border-ink hover:text-ink"
          >
            Unlist
          </button>
        ) : (
          <button
            type="submit"
            name="action"
            value="list"
            className="rounded-md bg-ink px-3 py-2 text-[13px] font-medium text-background transition hover:opacity-90"
          >
            List
          </button>
        )}
        {workspace.featured ? (
          <button
            type="submit"
            name="action"
            value="unfeature"
            className="rounded-md border border-border-subtle px-3 py-2 text-[13px] text-dim transition hover:border-ink hover:text-ink"
          >
            Unfeature
          </button>
        ) : (
          <button
            type="submit"
            name="action"
            value="feature"
            className="rounded-md border border-border-subtle px-3 py-2 text-[13px] text-dim transition hover:border-brand hover:text-brand"
          >
            Feature
          </button>
        )}
        <Link
          href={`/s/${workspace.id}`}
          className="rounded-md border border-border-subtle px-3 py-2 text-[13px] text-dim transition hover:border-ink hover:text-ink"
        >
          Open
        </Link>
      </form>
    </div>
  );
}

function Badge({
  children,
  tone = "gray",
}: {
  children: ReactNode;
  tone?: "gray" | "green" | "orange";
}) {
  const className =
    tone === "green"
      ? "border-green-500/30 text-green-600"
      : tone === "orange"
        ? "border-brand/35 text-brand"
        : "border-border-subtle text-muted";
  return (
    <span className={`rounded-md border px-1.5 py-0.5 font-mono text-[10px] uppercase ${className}`}>
      {children}
    </span>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface px-3 py-2">
      <div className="text-[16px] font-semibold tracking-normal text-ink">{value}</div>
      <div className="mt-0.5 text-[10px]">{label}</div>
    </div>
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
