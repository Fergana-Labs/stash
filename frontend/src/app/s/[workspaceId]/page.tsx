import Link from "next/link";
import { notFound } from "next/navigation";

import type { PublicWorkspaceDetail } from "../../../lib/api";
import ForkButton from "./ForkButton";

const BACKEND_ORIGIN =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

async function loadDetail(workspaceId: string): Promise<PublicWorkspaceDetail | null> {
  const res = await fetch(
    `${BACKEND_ORIGIN}/api/v1/discover/workspaces/${workspaceId}`,
    { next: { revalidate: 60 } }
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`discover fetch failed: ${res.status}`);
  return res.json();
}

export default async function PublicStashPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const detail = await loadDetail(workspaceId);
  if (!detail) notFound();

  const { workspace: ws, notebooks, tables, files, decks } = detail;
  const owner = ws.creator_display_name || ws.creator_name;

  return (
    <main className="mx-auto max-w-[1100px] px-7 py-12">
      <Link
        href="/discover"
        className="font-mono text-[12px] uppercase tracking-wider text-muted hover:text-ink"
      >
        ← Discover
      </Link>

      <header className="mt-6 flex flex-col gap-4 border-b border-border-subtle pb-8">
        <div className="flex items-start justify-between gap-6">
          <div>
            <h1 className="font-display text-[clamp(32px,4vw,48px)] font-black leading-[1.05] tracking-[-0.03em] text-ink">
              {ws.name}
            </h1>
            <p className="mt-2 text-[14px] text-dim">
              by {owner} · updated {relativeTime(ws.updated_at)}
            </p>
          </div>
          <div className="flex items-start gap-2">
            <ForkButton workspaceId={ws.id} defaultName={`${ws.name} (fork)`} />
            <Link
              href={`/login?next=${encodeURIComponent(`/workspaces/${ws.id}`)}`}
              className="rounded-lg border border-border px-4 py-2 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Sign in to join
            </Link>
          </div>
        </div>

        {ws.summary ? (
          <p className="max-w-[720px] text-[16px] leading-[1.55] text-foreground">{ws.summary}</p>
        ) : null}

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[11px] uppercase tracking-wider text-muted">
          <span>★ {ws.fork_count} forks</span>
          <span>{ws.member_count} members</span>
          <span>{ws.notebook_count} notebooks</span>
          <span>{ws.table_count} tables</span>
          <span>{ws.deck_count} decks</span>
          <span>{ws.file_count} files</span>
          <span>{ws.history_event_count} events</span>
        </div>

        {ws.tags?.length ? (
          <div className="flex flex-wrap gap-1.5">
            {ws.tags.map((t) => (
              <span
                key={t}
                className="rounded-md border border-border-subtle px-2 py-0.5 font-mono text-[10px] text-muted"
              >
                {t}
              </span>
            ))}
          </div>
        ) : null}

        {ws.forked_from_workspace_id ? (
          <p className="text-[12px] text-dim">
            Forked from{" "}
            <Link href={`/s/${ws.forked_from_workspace_id}`} className="text-brand hover:underline">
              another Stash
            </Link>
          </p>
        ) : null}
      </header>

      {ws.description ? (
        <section className="prose prose-invert mt-8 max-w-none text-[16px] leading-[1.65] text-foreground">
          <p>{ws.description}</p>
        </section>
      ) : null}

      <Section title="Notebooks" empty="No notebooks.">
        {notebooks.map((nb) => (
          <Row
            key={nb.id}
            href={`/s/${ws.id}/n/${nb.id}`}
            title={nb.name}
            subtitle={nb.description}
            meta={`${nb.page_count} page${nb.page_count === 1 ? "" : "s"} · updated ${relativeTime(nb.updated_at)}`}
          />
        ))}
      </Section>

      <Section title="Tables" empty="No tables.">
        {tables.map((t) => (
          <Row
            key={t.id}
            href={`/s/${ws.id}/t/${t.id}`}
            title={t.name}
            meta={`${t.row_count} row${t.row_count === 1 ? "" : "s"} · updated ${relativeTime(t.updated_at)}`}
          />
        ))}
      </Section>

      <Section title="Decks" empty="No decks.">
        {decks.map((d) => (
          <Row
            key={d.id}
            title={d.name}
            subtitle={d.description}
            meta={relativeTime(d.updated_at)}
          />
        ))}
      </Section>

      <Section title="Files" empty="No files.">
        {files.map((f) => (
          <Row
            key={f.id}
            title={f.name}
            meta={`${formatSize(f.size_bytes)} · ${relativeTime(f.created_at)}`}
          />
        ))}
      </Section>
    </main>
  );
}

function Section({
  title,
  empty,
  children,
}: {
  title: string;
  empty: string;
  children: React.ReactNode;
}) {
  const items = Array.isArray(children) ? children : [children];
  const filled = items.filter(Boolean);
  return (
    <section className="mt-10">
      <h2 className="font-display text-[18px] font-bold text-ink">{title}</h2>
      <div className="mt-3 divide-y divide-border-subtle border-y border-border-subtle">
        {filled.length === 0 ? (
          <p className="py-4 text-[13px] text-muted">{empty}</p>
        ) : (
          filled
        )}
      </div>
    </section>
  );
}

function Row({
  href,
  title,
  subtitle,
  meta,
}: {
  href?: string;
  title: string;
  subtitle?: string;
  meta?: string;
}) {
  const content = (
    <div className="flex items-center justify-between gap-4 py-3">
      <div className="min-w-0">
        <p className="truncate text-[15px] text-ink">{title}</p>
        {subtitle ? <p className="truncate text-[13px] text-dim">{subtitle}</p> : null}
      </div>
      {meta ? (
        <p className="shrink-0 font-mono text-[11px] uppercase tracking-wider text-muted">{meta}</p>
      ) : null}
    </div>
  );
  if (!href) return content;
  return (
    <Link href={href} className="block transition hover:bg-raised/40">
      {content}
    </Link>
  );
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 30) return `${d}d ago`;
  return `${Math.round(d / 30)}mo ago`;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}
