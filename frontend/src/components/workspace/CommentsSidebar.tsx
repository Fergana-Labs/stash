"use client";

import { useState } from "react";

import type { CommentThread } from "../../lib/types";

interface CommentsSidebarProps {
  threads: CommentThread[];
  activeThreadId: string | null;
  currentUserId: string;
  onActivate: (threadId: string) => void;
  onReply: (threadId: string, body: string) => Promise<void>;
  onSetResolved: (threadId: string, resolved: boolean) => Promise<void>;
}

export default function CommentsSidebar({
  threads,
  activeThreadId,
  currentUserId,
  onActivate,
  onReply,
  onSetResolved,
}: CommentsSidebarProps) {
  const open = threads.filter((t) => !t.resolved_at && !t.orphaned);
  const orphaned = threads.filter((t) => !t.resolved_at && t.orphaned);
  const resolved = threads.filter((t) => t.resolved_at);

  return (
    <aside className="mt-20 hidden lg:block">
      <div className="card-soft sticky top-16 max-h-[calc(100vh-6rem)] overflow-y-auto p-3.5">
        <div className="sys-label">Comments</div>
        {threads.length === 0 ? (
          <div className="mt-2 text-[12px] leading-relaxed text-muted">
            Select text in the page and click <b>Comment</b> to start a thread.
          </div>
        ) : (
          <div className="mt-3 flex flex-col gap-4">
            <Group
              label="Open"
              threads={open}
              empty="No open threads."
              activeThreadId={activeThreadId}
              currentUserId={currentUserId}
              onActivate={onActivate}
              onReply={onReply}
              onSetResolved={onSetResolved}
            />
            {orphaned.length > 0 && (
              <Group
                label="Orphaned"
                threads={orphaned}
                empty=""
                activeThreadId={activeThreadId}
                currentUserId={currentUserId}
                onActivate={onActivate}
                onReply={onReply}
                onSetResolved={onSetResolved}
                hint="The anchored text was deleted from the page. Resolve to clear."
              />
            )}
            {resolved.length > 0 && (
              <Group
                label="Resolved"
                threads={resolved}
                empty=""
                activeThreadId={activeThreadId}
                currentUserId={currentUserId}
                onActivate={onActivate}
                onReply={onReply}
                onSetResolved={onSetResolved}
                collapsedByDefault
              />
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

function Group({
  label,
  threads,
  empty,
  activeThreadId,
  currentUserId,
  onActivate,
  onReply,
  onSetResolved,
  hint,
  collapsedByDefault,
}: {
  label: string;
  threads: CommentThread[];
  empty: string;
  activeThreadId: string | null;
  currentUserId: string;
  onActivate: (threadId: string) => void;
  onReply: (threadId: string, body: string) => Promise<void>;
  onSetResolved: (threadId: string, resolved: boolean) => Promise<void>;
  hint?: string;
  collapsedByDefault?: boolean;
}) {
  const [expanded, setExpanded] = useState(!collapsedByDefault);
  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="sys-label flex w-full items-center justify-between"
        style={{ fontSize: 11 }}
      >
        <span>
          {label} ({threads.length})
        </span>
        <span>{expanded ? "−" : "+"}</span>
      </button>
      {expanded && (
        <div className="mt-2 flex flex-col gap-2">
          {hint && <div className="text-[11.5px] text-muted">{hint}</div>}
          {threads.length === 0 && empty && (
            <div className="text-[12px] text-muted">{empty}</div>
          )}
          {threads.map((t) => (
            <ThreadCard
              key={t.id}
              thread={t}
              active={t.id === activeThreadId}
              currentUserId={currentUserId}
              onActivate={onActivate}
              onReply={onReply}
              onSetResolved={onSetResolved}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ThreadCard({
  thread,
  active,
  currentUserId,
  onActivate,
  onReply,
  onSetResolved,
}: {
  thread: CommentThread;
  active: boolean;
  currentUserId: string;
  onActivate: (threadId: string) => void;
  onReply: (threadId: string, body: string) => Promise<void>;
  onSetResolved: (threadId: string, resolved: boolean) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    const body = draft.trim();
    if (!body) return;
    setSubmitting(true);
    try {
      await onReply(thread.id, body);
      setDraft("");
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleResolved() {
    await onSetResolved(thread.id, !thread.resolved_at);
  }

  // Suppress the author's own name on the lone first message to keep
  // the card tight; the timestamp + body already tell the story.
  const messages = thread.messages;

  return (
    <div
      onClick={() => onActivate(thread.id)}
      className={`rounded-md border px-2.5 py-2 text-[12.5px] ${
        active
          ? "border-[var(--color-brand-600)] bg-[var(--color-brand-50)]"
          : "border-border-subtle bg-raised/40"
      } cursor-pointer`}
    >
      <div className="mb-1 text-[11.5px] italic text-muted truncate">
        “{thread.quoted_text}”
      </div>
      <div className="flex flex-col gap-1.5">
        {messages.map((m) => (
          <div key={m.id} className="leading-snug">
            <span className="font-medium text-foreground">
              {m.author_id === currentUserId ? "You" : m.author_name || "Someone"}
            </span>
            <span className="text-muted"> · </span>
            <span className="text-muted text-[11px]">{relTime(m.created_at)}</span>
            <div className="text-foreground whitespace-pre-wrap">{m.body}</div>
          </div>
        ))}
      </div>
      {!thread.resolved_at && (
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            placeholder="Reply…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            onClick={(e) => e.stopPropagation()}
            disabled={submitting}
            className="flex-1 rounded-sm border border-border-subtle bg-background px-2 py-1 text-[12px] text-foreground disabled:opacity-60"
          />
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              toggleResolved();
            }}
            className="rounded-sm border border-border-subtle bg-background px-2 py-1 text-[11.5px] text-foreground hover:bg-raised"
          >
            Resolve
          </button>
        </div>
      )}
      {thread.resolved_at && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            toggleResolved();
          }}
          className="mt-2 text-[11.5px] text-muted underline hover:text-foreground"
        >
          Reopen
        </button>
      )}
    </div>
  );
}

function relTime(iso: string): string {
  const dt = new Date(iso);
  const secs = (Date.now() - dt.getTime()) / 1000;
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  if (secs < 86400 * 30) return `${Math.floor(secs / 86400)}d`;
  return dt.toLocaleDateString();
}
