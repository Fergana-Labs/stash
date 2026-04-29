import Link from "next/link";
import { notFound } from "next/navigation";

import HtmlPageView from "../../../components/workspace/HtmlPageView";
import ViewForkButton from "./ViewForkButton";

const BACKEND_ORIGIN =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

type ViewItemInlined = {
  object_type: "notebook" | "table" | "file" | "history";
  object_id: string;
  position: number;
  label: string;
  inline: Record<string, unknown>;
};

type ViewPublic = {
  view: {
    id: string;
    slug: string;
    title: string;
    description: string;
    cover_image_url: string | null;
    view_count: number;
    created_at: string;
    updated_at: string;
    workspace_id: string;
  };
  workspace_name: string;
  workspace_is_public: boolean;
  items: ViewItemInlined[];
};

async function loadView(slug: string): Promise<ViewPublic | null> {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/views/${slug}`, {
    next: { revalidate: 30 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`view fetch failed: ${res.status}`);
  return res.json();
}

export default async function ViewPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = await loadView(slug);
  if (!data) notFound();

  const { view, workspace_name, workspace_is_public, items } = data;

  return (
    <main className="mx-auto max-w-[900px] px-7 py-12">
      <header className="border-b border-border-subtle pb-8">
        <p className="font-mono text-[11px] uppercase tracking-wider text-muted">
          A View {workspace_is_public ? (
            <>
              from{" "}
              <Link href={`/s/${view.workspace_id}`} className="text-brand hover:underline">
                {workspace_name}
              </Link>
            </>
          ) : (
            <>from {workspace_name}</>
          )}
        </p>
        <h1 className="mt-3 font-display text-[clamp(32px,4vw,48px)] font-black leading-[1.05] tracking-[-0.03em] text-ink">
          {view.title}
        </h1>
        {view.description ? (
          <p className="mt-4 max-w-[680px] text-[16px] leading-[1.6] text-foreground">
            {view.description}
          </p>
        ) : null}
        <div className="mt-6 flex items-center justify-between gap-4">
          <p className="font-mono text-[11px] uppercase tracking-wider text-muted">
            {items.length} item{items.length === 1 ? "" : "s"} · viewed {view.view_count} time
            {view.view_count === 1 ? "" : "s"}
          </p>
          <ViewForkButton slug={view.slug} defaultName={view.title} />
        </div>
      </header>

      <nav className="mt-8 rounded-lg border border-border-subtle bg-raised/30 p-4">
        <p className="font-mono text-[11px] uppercase tracking-wider text-muted">In this View</p>
        <ol className="mt-2 space-y-1">
          {items.map((it, i) => (
            <li key={`${it.object_type}-${it.object_id}`} className="text-[14px]">
              <a href={`#item-${i}`} className="text-ink hover:text-brand">
                <span className="font-mono text-[11px] uppercase text-muted mr-2">
                  {it.object_type}
                </span>
                {it.label}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <div className="mt-10 space-y-12">
        {items.map((it, i) => (
          <Item key={`${it.object_type}-${it.object_id}`} idx={i} item={it} />
        ))}
      </div>
    </main>
  );
}

function Item({ idx, item }: { idx: number; item: ViewItemInlined }) {
  return (
    <section id={`item-${idx}`} className="scroll-mt-12">
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded border border-border-subtle px-2 py-0.5 font-mono text-[10px] uppercase text-muted">
          {item.object_type}
        </span>
        <h2 className="font-display text-[20px] font-bold text-ink">{item.label}</h2>
      </div>
      <div className="rounded-lg border border-border-subtle bg-raised/20 p-5">
        <ItemBody item={item} />
      </div>
    </section>
  );
}

function ItemBody({ item }: { item: ViewItemInlined }) {
  if (Object.keys(item.inline).length === 0) {
    return <p className="text-[13px] italic text-muted">This item is no longer available.</p>;
  }

  if (item.object_type === "notebook") {
    const inline = item.inline as {
      description?: string;
      pages?: {
        id: string;
        name: string;
        content_type?: "markdown" | "html";
        content_markdown: string;
        content_html?: string;
      }[];
    };
    return (
      <div>
        {inline.description ? (
          <p className="mb-4 text-[14px] text-dim">{inline.description}</p>
        ) : null}
        {(inline.pages ?? []).map((p) => (
          <div key={p.id} className="mb-6 last:mb-0">
            <h3 className="font-display text-[16px] font-bold text-ink">{p.name}</h3>
            {p.content_type === "html" ? (
              <div className="mt-2">
                <HtmlPageView html={p.content_html || ""} title={p.name} />
              </div>
            ) : (
              <pre className="mt-2 whitespace-pre-wrap break-words rounded bg-background p-3 font-mono text-[12px] leading-[1.5] text-foreground">
                {p.content_markdown || "(empty)"}
              </pre>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (item.object_type === "table") {
    const inline = item.inline as {
      description?: string;
      columns?: { name: string; type: string }[];
      rows?: { data: Record<string, unknown> }[];
    };
    const cols = inline.columns ?? [];
    const rows = inline.rows ?? [];
    return (
      <div>
        {inline.description ? (
          <p className="mb-3 text-[14px] text-dim">{inline.description}</p>
        ) : null}
        <div className="overflow-x-auto">
          <table className="min-w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle">
                {cols.map((c) => (
                  <th key={c.name} className="px-2 py-1 text-left font-mono text-[10px] uppercase text-muted">
                    {c.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-border-subtle/50">
                  {cols.map((c) => (
                    <td key={c.name} className="px-2 py-1 text-foreground">
                      {String(r.data[c.name] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (item.object_type === "file") {
    const inline = item.inline as { content_type?: string; size_bytes?: number };
    return (
      <p className="text-[13px] text-dim">
        {inline.content_type} · {formatSize(inline.size_bytes ?? 0)}
      </p>
    );
  }

  if (item.object_type === "history") {
    const inline = item.inline as {
      agent_name?: string;
      event_type?: string;
      content?: string;
      created_at?: string;
    };
    return (
      <div>
        <p className="font-mono text-[11px] uppercase text-muted">
          {inline.agent_name} · {inline.event_type} · {inline.created_at}
        </p>
        <pre className="mt-2 whitespace-pre-wrap break-words rounded bg-background p-3 font-mono text-[12px] leading-[1.5] text-foreground">
          {inline.content || ""}
        </pre>
      </div>
    );
  }

  return null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}
