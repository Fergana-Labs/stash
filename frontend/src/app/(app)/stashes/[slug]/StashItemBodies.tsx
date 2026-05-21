"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import HtmlPageView from "../../../../components/workspace/HtmlPageView";
import type { PublicStashItem } from "../../../../lib/api";

// Inline body renderers used on the /stashes/[slug] detail page when the
// stash contains a single page or single session — we render the content
// inline (read-only) instead of making the user click through. Multi-item
// tiles route to the native workspace viewer, which handles permissions
// and edit affordances natively.

interface InlineSessionEvent {
  agent_name?: string;
  event_type?: string;
  tool_name?: string | null;
  content?: string;
  created_at?: string;
}

export function PageBody({ item }: { item: PublicStashItem }) {
  const p = (item.inline as {
    page?: {
      content_type?: string;
      content_markdown?: string;
      content_html?: string;
      html_layout?: "responsive" | "fixed-aspect";
      name?: string;
    };
  }).page;
  if (!p) return null;
  if (p.content_type === "html") {
    return (
      <HtmlPageView
        html={p.content_html || ""}
        title={p.name || item.label}
        layout={p.html_layout}
      />
    );
  }
  return (
    <div className="markdown-content">
      <Markdown remarkPlugins={[remarkGfm]}>{p.content_markdown || ""}</Markdown>
    </div>
  );
}

export function FolderBody({ item }: { item: PublicStashItem }) {
  const inline = item.inline as {
    pages?: {
      id: string;
      name: string;
      content_type?: string;
      content_markdown?: string;
      content_html?: string;
      html_layout?: "responsive" | "fixed-aspect";
    }[];
    files?: {
      id: string;
      name: string;
      content_type?: string;
      size_bytes?: number;
      url?: string;
    }[];
  };
  const pages = inline.pages ?? [];
  const files = inline.files ?? [];
  if (pages.length === 0 && files.length === 0) {
    return <p className="text-[13px] text-muted">Folder is empty.</p>;
  }
  return (
    <div className="space-y-4">
      {pages.length > 0 && (
        <section>
          <h2 className="m-0 mb-2 font-display text-[14px] font-semibold text-foreground">
            Pages
          </h2>
          <div className="space-y-3">
            {pages.map((p) => (
              <div key={p.id} className="rounded-lg border border-border bg-base px-4 py-3">
                <h3 className="m-0 mb-2 font-display text-[14px] font-semibold text-foreground">
                  {p.name}
                </h3>
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
        </section>
      )}
      {files.length > 0 && (
        <section>
          <h2 className="m-0 mb-2 font-display text-[14px] font-semibold text-foreground">
            Files
          </h2>
          <div className="space-y-1.5">
            {files.map((f) => (
              <a
                key={f.id}
                href={f.url}
                target="_blank"
                rel="noreferrer"
                className="block rounded-md border border-border-subtle bg-base px-3 py-2 text-[13px] text-foreground hover:bg-raised"
              >
                <span className="block truncate font-medium">{f.name}</span>
                <span className="mt-0.5 block text-[11.5px] text-muted">
                  {f.content_type ?? "file"}
                  {f.size_bytes != null ? ` · ${formatSize(f.size_bytes)}` : ""}
                </span>
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function SessionBody({ item }: { item: PublicStashItem }) {
  const s = (item.inline as {
    session?: {
      agent_name?: string;
      started_at?: string | null;
      finished_at?: string | null;
      events?: InlineSessionEvent[];
    };
  }).session;
  if (!s) return null;
  const events = s.events ?? [];
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-base px-4 py-3 text-[13px] text-foreground">
        <div className="flex flex-wrap items-center gap-3 text-[11.5px] uppercase tracking-wide text-muted">
          {s.agent_name && <span>agent · {s.agent_name}</span>}
          {s.started_at && <span>started · {new Date(s.started_at).toLocaleString()}</span>}
          {s.finished_at && <span>ended · {new Date(s.finished_at).toLocaleString()}</span>}
        </div>
      </div>
      <div className="space-y-2">
        {events.map((event, i) => (
          <div
            key={`${event.created_at ?? "evt"}-${i}`}
            className="rounded-md border border-border-subtle bg-base/40 px-3 py-2 text-[12.5px]"
          >
            <div className="flex items-center gap-2 text-[10.5px] uppercase tracking-wide text-muted">
              <span>{event.event_type || "event"}</span>
              {event.tool_name && <span>· {event.tool_name}</span>}
              {event.created_at && (
                <span>· {new Date(event.created_at).toLocaleTimeString()}</span>
              )}
            </div>
            <pre className="mt-1.5 m-0 whitespace-pre-wrap font-sans text-[12.5px] leading-relaxed text-foreground">
              {event.content || ""}
            </pre>
          </div>
        ))}
        {events.length === 0 && (
          <p className="text-[12.5px] text-muted">No events recorded.</p>
        )}
      </div>
    </div>
  );
}
