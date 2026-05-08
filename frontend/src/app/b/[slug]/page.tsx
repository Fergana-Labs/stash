import type { Metadata } from "next";
import { notFound } from "next/navigation";

const BACKEND_ORIGIN =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

type StashArtifact = {
  id: string;
  file_path: string;
  size_bytes: number;
  created_at: string;
};

type StashData = {
  id: string;
  workspace_id: string;
  session_id: string;
  slug: string;
  agent_name: string;
  cwd: string | null;
  status: "uploading" | "summarizing" | "ready" | "failed";
  summary: string | null;
  files_touched: string[];
  artifact_count: number;
  has_transcript: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
  artifacts: StashArtifact[];
};

async function loadStash(slug: string): Promise<StashData | null> {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/stashes/${slug}`, {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`stash fetch failed: ${res.status}`);
  return res.json();
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const data = await loadStash(slug);
  if (!data) return { title: "Stash not found" };
  const title = `Stash · ${data.agent_name || "Session"}`;
  const description =
    data.summary?.slice(0, 160) ||
    `A stash with ${data.artifact_count} artifact${data.artifact_count === 1 ? "" : "s"}.`;
  return {
    title,
    description,
    openGraph: { title, description, type: "article", url: `/b/${slug}`, siteName: "Stash" },
    twitter: { card: "summary", title, description },
  };
}

export default async function StashPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = await loadStash(slug);
  if (!data) notFound();

  const statusLabel: Record<string, { text: string; color: string }> = {
    uploading: { text: "Uploading artifacts...", color: "text-amber-400" },
    summarizing: { text: "Generating summary...", color: "text-blue-400" },
    ready: { text: "Ready", color: "text-emerald-400" },
    failed: { text: "Summary unavailable", color: "text-red-400" },
  };
  const st = statusLabel[data.status] || statusLabel.uploading;

  return (
    <main className="mx-auto max-w-[900px] px-7 py-12">
      <header className="border-b border-border-subtle pb-8">
        <p className="font-mono text-[11px] uppercase tracking-wider text-muted">
          Stash
        </p>
        <h1 className="mt-3 font-display text-[clamp(28px,3.5vw,40px)] font-black leading-[1.1] tracking-[-0.03em] text-ink">
          {data.agent_name ? `${data.agent_name} session` : "Coding session"}
        </h1>
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-[12px] text-muted">
          <span className={st.color}>● {st.text}</span>
          {data.cwd ? <span title="Working directory">{data.cwd}</span> : null}
          <span>{new Date(data.created_at).toLocaleString()}</span>
        </div>
        <div className="mt-4 font-mono text-[11px] text-muted">
          {data.artifact_count} artifact{data.artifact_count === 1 ? "" : "s"}
          {data.has_transcript ? " · transcript available" : ""}
        </div>
      </header>

      {/* Summary */}
      {data.summary ? (
        <section className="mt-8">
          <h2 className="font-display text-[18px] font-bold text-ink">Summary</h2>
          <div className="mt-3 whitespace-pre-wrap text-[14px] leading-[1.7] text-foreground">
            {data.summary}
          </div>
        </section>
      ) : data.status === "summarizing" || data.status === "uploading" ? (
        <section className="mt-8">
          <h2 className="font-display text-[18px] font-bold text-ink">Summary</h2>
          <p className="mt-3 text-[14px] italic text-muted">
            Summary is being generated. Refresh this page in a moment.
          </p>
        </section>
      ) : null}

      {/* Artifacts sidebar / file tree */}
      {data.artifacts.length > 0 ? (
        <section className="mt-8">
          <h2 className="font-display text-[18px] font-bold text-ink">Artifacts</h2>
          <div className="mt-3 rounded-lg border border-border-subtle bg-raised/20">
            {data.artifacts.map((a) => (
              <a
                key={a.id}
                href={`${BACKEND_ORIGIN}/api/v1/stashes/${slug}/files/${a.id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between border-b border-border-subtle/50 px-4 py-2 last:border-b-0 hover:bg-raised/40"
              >
                <span className="font-mono text-[13px] text-ink">{a.file_path}</span>
                <span className="font-mono text-[11px] text-muted">{formatSize(a.size_bytes)}</span>
              </a>
            ))}
          </div>
        </section>
      ) : null}

      {/* Transcript link */}
      {data.has_transcript ? (
        <section className="mt-8">
          <h2 className="font-display text-[18px] font-bold text-ink">Transcript</h2>
          <p className="mt-3 text-[14px] text-foreground">
            <a
              href={`${BACKEND_ORIGIN}/api/v1/stashes/${slug}/transcript`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand hover:underline"
            >
              Download full session transcript →
            </a>
          </p>
        </section>
      ) : null}

      {/* Agent-readable notice */}
      <footer className="mt-12 border-t border-border-subtle pt-6">
        <p className="font-mono text-[11px] text-muted">
          Agents: fetch this stash as structured markdown at{" "}
          <code className="rounded bg-raised px-1 py-0.5">
            {BACKEND_ORIGIN}/api/v1/stashes/{slug}?format=text
          </code>
        </p>
      </footer>
    </main>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
