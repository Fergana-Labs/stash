"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";

import type { CommentThread } from "../../lib/types";

interface CommentsSidebarProps {
  threads: CommentThread[];
  activeThreadId: string | null;
  currentUserId: string;
  anchorTops?: Record<string, number>;
  onActivate: (threadId: string) => void;
  onReply: (threadId: string, body: string) => Promise<void>;
  onSetResolved: (threadId: string, resolved: boolean) => Promise<void>;
  onDeleteThread: (threadId: string) => Promise<void>;
  onDeleteMessage: (threadId: string, messageId: string) => Promise<void>;
}

const CARD_GAP = 8;
const ESTIMATED_CARD_HEIGHT = 124;

export default function CommentsSidebar({
  threads,
  activeThreadId,
  currentUserId,
  anchorTops = {},
  onActivate,
  onReply,
  onSetResolved,
  onDeleteThread,
  onDeleteMessage,
}: CommentsSidebarProps) {
  const open = threads.filter((t) => !t.resolved_at && !t.orphaned);
  const orphaned = threads.filter((t) => !t.resolved_at && t.orphaned);
  const resolved = threads.filter((t) => t.resolved_at);

  if (threads.length === 0) return null;

  if (open.some((thread) => hasAnchorTop(anchorTops, thread.id))) {
    return (
      <AlignedComments
        open={open}
        orphaned={orphaned}
        resolved={resolved}
        activeThreadId={activeThreadId}
        currentUserId={currentUserId}
        anchorTops={anchorTops}
        onActivate={onActivate}
        onReply={onReply}
        onSetResolved={onSetResolved}
        onDeleteThread={onDeleteThread}
        onDeleteMessage={onDeleteMessage}
      />
    );
  }

  return (
    <aside>
      <div className="card-soft max-h-[calc(100vh-6rem)] overflow-y-auto p-3.5">
        <div className="sys-label">Comments</div>
        <div className="mt-3 flex flex-col gap-4">
          {open.length > 0 && (
            <Group
              label="Open"
              threads={open}
              activeThreadId={activeThreadId}
              currentUserId={currentUserId}
              onActivate={onActivate}
              onReply={onReply}
              onSetResolved={onSetResolved}
              onDeleteThread={onDeleteThread}
              onDeleteMessage={onDeleteMessage}
            />
          )}
          {orphaned.length > 0 && (
            <Group
              label="Orphaned"
              threads={orphaned}
              activeThreadId={activeThreadId}
              currentUserId={currentUserId}
              onActivate={onActivate}
              onReply={onReply}
              onSetResolved={onSetResolved}
              onDeleteThread={onDeleteThread}
              onDeleteMessage={onDeleteMessage}
              hint="The anchored text was deleted from the page. Resolve to clear."
            />
          )}
          {resolved.length > 0 && (
            <Group
              label="Resolved"
              threads={resolved}
              activeThreadId={activeThreadId}
              currentUserId={currentUserId}
              onActivate={onActivate}
              onReply={onReply}
              onSetResolved={onSetResolved}
              onDeleteThread={onDeleteThread}
              onDeleteMessage={onDeleteMessage}
              collapsedByDefault
            />
          )}
        </div>
      </div>
    </aside>
  );
}

function AlignedComments({
  open,
  orphaned,
  resolved,
  activeThreadId,
  currentUserId,
  anchorTops,
  onActivate,
  onReply,
  onSetResolved,
  onDeleteThread,
  onDeleteMessage,
}: {
  open: CommentThread[];
  orphaned: CommentThread[];
  resolved: CommentThread[];
  activeThreadId: string | null;
  currentUserId: string;
  anchorTops: Record<string, number>;
  onActivate: (threadId: string) => void;
  onReply: (threadId: string, body: string) => Promise<void>;
  onSetResolved: (threadId: string, resolved: boolean) => Promise<void>;
  onDeleteThread: (threadId: string) => Promise<void>;
  onDeleteMessage: (threadId: string, messageId: string) => Promise<void>;
}) {
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [cardHeights, setCardHeights] = useState<Record<string, number>>({});
  const sortedOpen = useMemo(
    () => sortThreadsByAnchorTop(open, anchorTops),
    [open, anchorTops],
  );
  const layout = useMemo(
    () => buildThreadLayout(sortedOpen, anchorTops, cardHeights),
    [sortedOpen, anchorTops, cardHeights],
  );

  useLayoutEffect(() => {
    const next: Record<string, number> = {};
    for (const thread of sortedOpen) {
      const node = cardRefs.current[thread.id];
      if (node) next[thread.id] = Math.ceil(node.getBoundingClientRect().height);
    }
    setCardHeights((current) => (sameNumberMap(current, next) ? current : next));
  }, [sortedOpen]);

  return (
    <aside className="relative">
      <div className="relative" style={{ minHeight: layout.height }}>
        {layout.items.map(({ thread, top }) => (
          <div
            key={thread.id}
            ref={(node) => {
              cardRefs.current[thread.id] = node;
            }}
            className="absolute left-0 right-0"
            style={{ top }}
          >
            <ThreadCard
              thread={thread}
              active={thread.id === activeThreadId}
              currentUserId={currentUserId}
              onActivate={onActivate}
              onReply={onReply}
              onSetResolved={onSetResolved}
              onDeleteThread={onDeleteThread}
              onDeleteMessage={onDeleteMessage}
            />
          </div>
        ))}
      </div>

      {(orphaned.length > 0 || resolved.length > 0) && (
        <div className="card-soft mt-4 p-3.5">
          <div className="sys-label">Comments</div>
          <div className="mt-3 flex flex-col gap-4">
            {orphaned.length > 0 && (
              <Group
                label="Orphaned"
                threads={orphaned}
                activeThreadId={activeThreadId}
                currentUserId={currentUserId}
                onActivate={onActivate}
                onReply={onReply}
                onSetResolved={onSetResolved}
                onDeleteThread={onDeleteThread}
                onDeleteMessage={onDeleteMessage}
                hint="The anchored text was deleted from the page. Resolve to clear."
              />
            )}
            {resolved.length > 0 && (
              <Group
                label="Resolved"
                threads={resolved}
                activeThreadId={activeThreadId}
                currentUserId={currentUserId}
                onActivate={onActivate}
                onReply={onReply}
                onSetResolved={onSetResolved}
                onDeleteThread={onDeleteThread}
                onDeleteMessage={onDeleteMessage}
                collapsedByDefault
              />
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

function sortThreadsByAnchorTop(
  threads: CommentThread[],
  anchorTops: Record<string, number>,
): CommentThread[] {
  return [...threads].sort((a, b) => {
    const aTop = anchorTops[a.id];
    const bTop = anchorTops[b.id];
    const aHasTop = typeof aTop === "number";
    const bHasTop = typeof bTop === "number";
    if (aHasTop && bHasTop) return aTop - bTop;
    if (aHasTop) return -1;
    if (bHasTop) return 1;
    return 0;
  });
}

function buildThreadLayout(
  threads: CommentThread[],
  anchorTops: Record<string, number>,
  cardHeights: Record<string, number>,
): { items: { thread: CommentThread; top: number }[]; height: number } {
  let nextTop = 0;
  const items = threads.map((thread) => {
    const anchorTop = anchorTops[thread.id];
    const desiredTop = typeof anchorTop === "number" ? Math.max(0, anchorTop) : nextTop;
    const top = Math.max(desiredTop, nextTop);
    const height = cardHeights[thread.id] ?? ESTIMATED_CARD_HEIGHT;
    nextTop = top + height + CARD_GAP;
    return { thread, top };
  });
  return { items, height: Math.max(0, nextTop - CARD_GAP) };
}

function hasAnchorTop(anchorTops: Record<string, number>, threadId: string): boolean {
  return typeof anchorTops[threadId] === "number";
}

function sameNumberMap(a: Record<string, number>, b: Record<string, number>): boolean {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) return false;
  return aKeys.every((key) => a[key] === b[key]);
}

function Group({
  label,
  threads,
  activeThreadId,
  currentUserId,
  onActivate,
  onReply,
  onSetResolved,
  onDeleteThread,
  onDeleteMessage,
  hint,
  collapsedByDefault,
}: {
  label: string;
  threads: CommentThread[];
  activeThreadId: string | null;
  currentUserId: string;
  onActivate: (threadId: string) => void;
  onReply: (threadId: string, body: string) => Promise<void>;
  onSetResolved: (threadId: string, resolved: boolean) => Promise<void>;
  onDeleteThread: (threadId: string) => Promise<void>;
  onDeleteMessage: (threadId: string, messageId: string) => Promise<void>;
  hint?: string;
  collapsedByDefault?: boolean;
}) {
  const [expanded, setExpanded] = useState(!collapsedByDefault);
  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="sys-label flex w-full cursor-pointer items-center justify-between"
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
          {threads.map((t) => (
            <ThreadCard
              key={t.id}
              thread={t}
              active={t.id === activeThreadId}
              currentUserId={currentUserId}
              onActivate={onActivate}
              onReply={onReply}
              onSetResolved={onSetResolved}
              onDeleteThread={onDeleteThread}
              onDeleteMessage={onDeleteMessage}
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
  onDeleteThread,
  onDeleteMessage,
}: {
  thread: CommentThread;
  active: boolean;
  currentUserId: string;
  onActivate: (threadId: string) => void;
  onReply: (threadId: string, body: string) => Promise<void>;
  onSetResolved: (threadId: string, resolved: boolean) => Promise<void>;
  onDeleteThread: (threadId: string) => Promise<void>;
  onDeleteMessage: (threadId: string, messageId: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const canDeleteThread = thread.created_by === currentUserId;

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
      data-comment-thread-id={thread.id}
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
        {messages.map((m) => {
          const own = m.author_id === currentUserId;
          return (
            <div key={m.id} className="group/msg leading-snug">
              <div className="flex items-baseline gap-1">
                <span className="font-medium text-foreground">
                  {own ? "You" : m.author_name || "Someone"}
                </span>
                <span className="text-muted">·</span>
                <span className="text-muted text-[11px]">{relTime(m.created_at)}</span>
                {own && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteMessage(thread.id, m.id);
                    }}
                    title="Delete comment"
                    className="ml-auto cursor-pointer px-1 text-[11px] leading-none text-muted opacity-0 transition-opacity hover:text-red-500 group-hover/msg:opacity-100"
                  >
                    ×
                  </button>
                )}
              </div>
              <div className="text-foreground whitespace-pre-wrap">{m.body}</div>
            </div>
          );
        })}
      </div>
      {!thread.resolved_at && (
        <div className="mt-2 flex flex-col gap-1.5">
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
            className="w-full min-w-0 rounded-sm border border-border-subtle bg-background px-2 py-1 text-[12px] text-foreground disabled:opacity-60"
          />
          <div className="flex items-center justify-end gap-2">
            {canDeleteThread && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteThread(thread.id);
                }}
                className="cursor-pointer text-[11px] text-muted underline hover:text-red-500"
              >
                Delete
              </button>
            )}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                toggleResolved();
              }}
              className="cursor-pointer rounded-sm border border-border-subtle bg-background px-2 py-0.5 text-[11px] text-muted hover:bg-raised hover:text-foreground"
            >
              Resolve
            </button>
          </div>
        </div>
      )}
      {thread.resolved_at && (
        <div className="mt-2 flex items-center gap-3">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              toggleResolved();
            }}
            className="cursor-pointer text-[11.5px] text-muted underline hover:text-foreground"
          >
            Reopen
          </button>
          {canDeleteThread && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDeleteThread(thread.id);
              }}
              className="cursor-pointer text-[11.5px] text-muted underline hover:text-red-500"
            >
              Delete
            </button>
          )}
        </div>
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
