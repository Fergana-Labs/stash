"use client";

import { useState } from "react";

import { addComment } from "../actions";
import { timeAgo } from "../_lib/time";
import type { PasteComment } from "../_lib/paste";

// Google-Docs-style right rail: the comment thread list plus an
// unanchored composer. Anchored comments arrive from the page's
// selection flow (the pill popover); this rail just displays them.
export default function CommentsRail({
  slug,
  comments,
  onCommentAdded,
  headerExtra,
}: {
  slug: string;
  comments: PasteComment[];
  onCommentAdded: (comment: PasteComment) => void;
  headerExtra?: React.ReactNode;
}) {
  const [composerOpen, setComposerOpen] = useState(false);

  async function submit(input: { author_name: string; body: string }) {
    const result = await addComment(slug, {
      author_name: input.author_name,
      body: input.body,
      quoted_text: "",
      prefix: "",
      suffix: "",
    });
    if (result.status === "error") return result.message;
    onCommentAdded(result.comment as PasteComment);
    setComposerOpen(false);
    return "";
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-[15px] font-semibold text-ink">
          Comments{comments.length > 0 && ` (${comments.length})`}
        </h2>
        {!composerOpen && (
          <button
            type="button"
            onClick={() => setComposerOpen(true)}
            className="text-[12.5px] font-medium text-dim hover:text-ink"
          >
            Add
          </button>
        )}
      </div>
      {headerExtra}
      {comments.length === 0 && !composerOpen && (
        <p className="mt-2 text-[12.5px] leading-relaxed text-muted">
          No comments yet. Select any text on the page to comment on it.
        </p>
      )}
      <ul className="mt-3 space-y-2.5">
        {comments.map((comment) => (
          <li key={comment.id} className="rounded-lg border border-border bg-white p-3">
            <p className="flex items-baseline gap-2 text-[12px] text-muted">
              <span className="font-medium text-ink">{comment.author_name || "Anonymous"}</span>
              {timeAgo(comment.created_at)}
            </p>
            {comment.quoted_text && (
              <p className="mt-1 truncate border-l-2 border-brand/60 pl-2 text-[12px] italic text-dim">
                {comment.quoted_text}
              </p>
            )}
            <p className="mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
              {comment.body}
            </p>
          </li>
        ))}
      </ul>
      {composerOpen && (
        <div className="mt-3">
          <CommentComposer quoted="" onCancel={() => setComposerOpen(false)} onSubmit={submit} />
        </div>
      )}
    </div>
  );
}

export function CommentComposer({
  quoted,
  onCancel,
  onSubmit,
}: {
  quoted: string;
  onCancel: () => void;
  onSubmit: (input: { author_name: string; body: string }) => Promise<string>;
}) {
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  async function send() {
    if (!body.trim() || sending) return;
    setSending(true);
    const message = await onSubmit({ author_name: name, body });
    setSending(false);
    setError(message);
  }

  return (
    <div className="w-full max-w-[280px] rounded-lg border border-border bg-white p-3 shadow-[0_8px_24px_-6px_rgba(0,0,0,0.25)]">
      {quoted && (
        <p className="mb-2 truncate border-l-2 border-brand/60 pl-2 text-[12px] italic text-dim">
          {quoted}
        </p>
      )}
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Name (optional)"
        maxLength={60}
        className="h-8 w-full rounded-md border border-border bg-white px-2.5 text-[13px] text-ink placeholder:text-muted focus:border-brand focus:outline-none"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Add a comment…"
        autoFocus
        className="mt-2 min-h-[64px] w-full resize-y rounded-md border border-border bg-white p-2.5 text-[13px] text-ink placeholder:text-muted focus:border-brand focus:outline-none"
      />
      {error && <p className="mt-1 text-[12px] text-red-600">{error}</p>}
      <div className="mt-2 flex items-center justify-end gap-2">
        <button type="button" onClick={onCancel} className="text-[13px] text-dim hover:text-ink">
          Cancel
        </button>
        <button
          type="button"
          onClick={send}
          disabled={!body.trim() || sending}
          className="inline-flex h-8 items-center rounded-md bg-brand px-3 text-[13px] font-medium text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {sending ? "Posting…" : "Comment"}
        </button>
      </div>
    </div>
  );
}
