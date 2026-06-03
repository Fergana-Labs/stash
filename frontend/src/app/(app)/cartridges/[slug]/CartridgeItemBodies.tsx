"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import HtmlPageView from "../../../../components/workspace/HtmlPageView";
import type { PublicCartridgeItem } from "../../../../lib/api";

// Inline body renderers used on the /cartridges/[slug] detail page when the
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

export function PageBody({ item }: { item: PublicCartridgeItem }) {
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

export function FolderBody({ item }: { item: PublicCartridgeItem }) {
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

// Project a history_events.event_type into the user/assistant axis the
// session viewer renders. Mirrors backend/routers/transcripts.py
// _event_role — tool_use/tool_result fold into "assistant" so the
// timeline shows tool calls inline with assistant turns.
function roleForEventType(t: string | undefined): "user" | "assistant" | null {
  if (!t) return null;
  if (t === "user_message" || t === "user_prompt" || t === "prompt" || t === "user") return "user";
  if (
    t === "assistant_message" ||
    t === "assistant" ||
    t === "tool_use" ||
    t === "tool_call" ||
    t === "tool_result"
  )
    return "assistant";
  return null;
}

const AVATAR_PALETTE: { bg: string; fg: string }[] = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-orange-200", fg: "text-orange-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-teal-200", fg: "text-teal-800" },
];

function avatarFor(name: string) {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

export function SessionBody({ item }: { item: PublicCartridgeItem }) {
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
      <div className="space-y-1">
        {events.map((event, i) => (
          <SessionTurn
            key={`${event.created_at ?? "evt"}-${i}`}
            event={event}
            agentName={s.agent_name}
          />
        ))}
        {events.length === 0 && (
          <p className="text-[12.5px] text-muted">No events recorded.</p>
        )}
      </div>
    </div>
  );
}

function SessionTurn({
  event,
  agentName,
}: {
  event: InlineSessionEvent;
  agentName?: string;
}) {
  const role = roleForEventType(event.event_type);
  // Skip event types the viewer can't classify (e.g. session_end) —
  // they're metadata, not content the visitor needs to read inline.
  if (!role) return null;

  const isAgent = role === "assistant";
  const isTool = event.event_type === "tool_use" || event.event_type === "tool_result";
  const name = isAgent ? agentName || "agent" : "user";
  const avatar = avatarFor(name);
  const time = event.created_at
    ? new Date(event.created_at).toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      })
    : undefined;

  return (
    <div className="msg-row group scroll-mt-16 rounded-md px-2 py-2">
      <div className="flex gap-3">
        <span
          className={
            "inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-semibold " +
            avatar.bg +
            " " +
            avatar.fg
          }
        >
          {initials(name)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 text-[12.5px]">
            <span className="font-semibold text-foreground">{name}</span>
            {isAgent ? (
              <span className="tag tag-agent">agent</span>
            ) : (
              <span className="tag tag-human">human</span>
            )}
            {event.tool_name && (
              <span className="rounded bg-surface px-1.5 py-0 font-mono text-[10.5px] text-dim ring-1 ring-border">
                {event.tool_name}
              </span>
            )}
            <span className="flex-1" />
            {time && (
              <span className="sys-label" style={{ fontSize: 10 }}>
                {time}
              </span>
            )}
          </div>
          <div
            className={
              "mt-1 whitespace-pre-wrap leading-relaxed text-foreground " +
              (isTool
                ? "rounded-md border border-border-subtle bg-surface px-2.5 py-2 font-mono text-[12px]"
                : "text-[13.5px]")
            }
          >
            {event.content || ""}
          </div>
        </div>
      </div>
    </div>
  );
}
