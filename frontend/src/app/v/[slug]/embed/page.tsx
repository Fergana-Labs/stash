import { notFound } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import HtmlPageView from "../../../../components/workspace/HtmlPageView";

const BACKEND_ORIGIN = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

type ViewItemInlined = {
  object_type: "folder" | "page" | "table" | "file" | "history";
  object_id: string;
  position: number;
  label: string;
  inline: Record<string, unknown>;
};

type ViewPublic = {
  view: { id: string; slug: string; title: string };
  items: ViewItemInlined[];
};

async function loadView(slug: string): Promise<ViewPublic | null> {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/views/${slug}`, {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`view fetch failed: ${res.status}`);
  return res.json();
}

export default async function EmbedView({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = await loadView(slug);
  if (!data) notFound();
  return (
    <main className="px-4 py-4">
      <h1 className="mb-3 font-display text-[18px] font-bold text-ink">{data.view.title}</h1>
      <div className="space-y-6">
        {data.items.map((it, i) => (
          <ItemBody key={`${it.object_type}-${it.object_id}-${i}`} item={it} />
        ))}
      </div>
      <p className="mt-4 text-right font-mono text-[10px] uppercase tracking-wider text-muted">
        <a href={`/v/${slug}`} target="_blank" rel="noreferrer" className="hover:text-ink">
          on Stash ↗
        </a>
      </p>
    </main>
  );
}

function ItemBody({ item }: { item: ViewItemInlined }) {
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
      </div>
    );
  }
  return <p className="text-[12px] text-muted">{item.label}</p>;
}
