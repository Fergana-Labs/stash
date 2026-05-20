import { notFound } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import HtmlPageView from "../../../../components/workspace/HtmlPageView";

const BACKEND_ORIGIN = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

type StashItemInlined = {
  object_type: "folder" | "page" | "table" | "file" | "session";
  object_id: string;
  position: number;
  label: string;
  inline: Record<string, unknown>;
};

type PublicStash = {
  stash: { id: string; slug: string; title: string };
  items: StashItemInlined[];
};

async function loadStash(slug: string): Promise<PublicStash | null> {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/stashes/${slug}`, {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`stash fetch failed: ${res.status}`);
  return res.json();
}

export default async function StashEmbed({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = await loadStash(slug);
  if (!data) notFound();
  return (
    <main className="px-4 py-4">
      <h1 className="mb-3 font-display text-[18px] font-bold text-ink">{data.stash.title}</h1>
      <div className="space-y-6">
        {data.items.map((it, i) => (
          <ItemBody key={`${it.object_type}-${it.object_id}-${i}`} item={it} />
        ))}
      </div>
      <p className="mt-4 text-right font-mono text-[10px] uppercase tracking-wider text-muted">
        <a href={`/stashes/${slug}`} target="_blank" rel="noreferrer" className="hover:text-ink">
          on Stash ↗
        </a>
      </p>
    </main>
  );
}

function ItemBody({ item }: { item: StashItemInlined }) {
  if (Object.keys(item.inline).length === 0) {
    return <p className="text-[12px] italic text-muted">Item unavailable.</p>;
  }
  if (item.object_type === "page") {
    const p = (item.inline as { page?: { content_type?: string; content_markdown?: string; content_html?: string; html_layout?: "responsive" | "fixed-aspect"; name?: string } }).page;
    if (!p) return null;
    return p.content_type === "html" ? (
      <HtmlPageView
        html={p.content_html || ""}
        title={p.name || item.label}
        layout={p.html_layout}
      />
    ) : (
      <div className="markdown-content">
        <Markdown remarkPlugins={[remarkGfm]}>{p.content_markdown || ""}</Markdown>
      </div>
    );
  }
  if (item.object_type === "folder") {
    const inline = item.inline as {
      pages?: { id: string; name: string; content_type?: string; content_markdown?: string; content_html?: string; html_layout?: "responsive" | "fixed-aspect" }[];
      files?: { id: string; name: string; content_type?: string; size_bytes?: number; url?: string }[];
    };
    return (
      <div className="space-y-4">
        {(inline.pages ?? []).map((p) => (
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
        {(inline.files ?? []).map((file) => (
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
    );
  }
  if (item.object_type === "session") {
    const session = (item.inline as {
      session?: { events?: { content: string; created_at: string }[] };
    }).session;
    if (!session) return null;
    return (
      <div className="space-y-3 text-[13px] leading-relaxed text-foreground">
        {(session.events ?? []).slice(0, 20).map((event, idx) => (
          <p key={`${event.created_at}-${idx}`} className="whitespace-pre-wrap">
            {event.content}
          </p>
        ))}
      </div>
    );
  }
  return <p className="text-[12px] text-muted">{item.label}</p>;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
