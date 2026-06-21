import { notFound } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { SSR_BACKEND_ORIGIN as BACKEND_ORIGIN } from "@/lib/backendOrigin";

import HtmlPageView from "@/components/workspace/HtmlPageView";

type EmbedPage = {
  id: string;
  name: string;
  content_type?: string;
  content_markdown?: string;
  content_html?: string;
  html_layout?: "responsive" | "fixed-aspect";
};

type EmbedFile = {
  id: string;
  name: string;
  content_type?: string;
  size_bytes?: number;
  url?: string;
};

type PublicSkill = {
  skill: { id: string; slug: string; title: string };
  contents: { pages: EmbedPage[]; files: EmbedFile[] };
};

async function loadSkill(slug: string): Promise<PublicSkill | null> {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/skills/${slug}`, {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`skill fetch failed: ${res.status}`);
  return res.json();
}

export default async function SkillEmbed({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = await loadSkill(slug);
  if (!data) notFound();
  return (
    <main className="px-4 py-4">
      <h1 className="mb-3 font-display text-[18px] font-bold text-ink">{data.skill.title}</h1>
      <div className="space-y-6">
        {data.contents.pages.map((p) => (
          <div key={p.id}>
            <h2 className="mb-2 font-display text-[15px] font-bold text-ink">{p.name}</h2>
            {p.content_type === "html" ? (
              <HtmlPageView
                html={p.content_html || ""}
                title={p.name}
                layout={p.html_layout}
              />
            ) : (
              <div className="markdown-content">
                <Markdown remarkPlugins={[remarkGfm]}>{p.content_markdown || ""}</Markdown>
              </div>
            )}
          </div>
        ))}
        {data.contents.files.map((file) => (
          <a
            key={file.id}
            href={file.url}
            target="_blank"
            rel="noreferrer"
            className="block rounded-md border border-border-subtle bg-base px-3 py-2 text-[12px] text-foreground"
          >
            <span className="block truncate font-medium">{file.name}</span>
            <span className="mt-0.5 block text-muted">
              {file.content_type} · {formatSize(file.size_bytes ?? 0)}
            </span>
          </a>
        ))}
      </div>
      <p className="mt-4 text-right font-mono text-[10px] uppercase tracking-wider text-muted">
        <a href={`/skills/${slug}`} target="_blank" rel="noreferrer" className="hover:text-ink">
          on Stash ↗
        </a>
      </p>
    </main>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
