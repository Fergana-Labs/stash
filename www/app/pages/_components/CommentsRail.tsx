"use client";

import { useEffect, useMemo, useState } from "react";

import { addComment, deleteComment } from "../actions";
import { timeAgo } from "../_lib/time";
import type { PasteComment } from "../_lib/paste";

const NAME_KEY = "stash-pages-comment-name";

// Google-Docs-style right rail: threads (top-level comments + their
// replies) plus composers. Comments created this session carry their
// edit_token, so their author can delete them; on the edit page the page
// owner's token (pageToken) can delete anything (moderation).
export default function CommentsRail({
  slug,
  comments,
  onCommentAdded,
  onCommentDeleted,
  pageToken,
  headerExtra,
}: {
  slug: string;
  comments: PasteComment[];
  onCommentAdded: (comment: PasteComment) => void;
  onCommentDeleted: (id: string) => void;
  pageToken?: string;
  headerExtra?: React.ReactNode;
}) {
  const [composerOpen, setComposerOpen] = useState(false);

  // Top-level comments in order, each with its replies grouped underneath.
  const threads = useMemo(() => {
    const tops = comments.filter((c) => !c.parent_id);
    const repliesByParent = new Map<string, PasteComment[]>();
    for (const c of comments) {
      if (!c.parent_id) continue;
      const list = repliesByParent.get(c.parent_id) ?? [];
      list.push(c);
      repliesByParent.set(c.parent_id, list);
    }
    return tops.map((top) => ({ top, replies: repliesByParent.get(top.id) ?? [] }));
  }, [comments]);

  function deleteTokenFor(comment: PasteComment): string | null {
    return pageToken ?? comment.edit_token ?? null;
  }

  async function remove(comment: PasteComment) {
    const token = deleteTokenFor(comment);
    if (!token) return;
    const result = await deleteComment(slug, comment.id, token);
    if (result.status === "ok") onCommentDeleted(comment.id);
  }

  async function submitTopLevel(input: { author_name: string; body: string }) {
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
        {threads.map(({ top, replies }) => (
          <li key={top.id} className="rounded-lg border border-border bg-white p-3">
            <CommentBody comment={top} canDelete={!!deleteTokenFor(top)} onDelete={() => remove(top)} />
            {replies.length > 0 && (
              <ul className="mt-2 space-y-2 border-l-2 border-border-subtle pl-3">
                {replies.map((reply) => (
                  <li key={reply.id}>
                    <CommentBody
                      comment={reply}
                      canDelete={!!deleteTokenFor(reply)}
                      onDelete={() => remove(reply)}
                    />
                  </li>
                ))}
              </ul>
            )}
            <ReplyControl slug={slug} parentId={top.id} onReplyAdded={onCommentAdded} />
          </li>
        ))}
      </ul>
      {composerOpen && (
        <div className="mt-3">
          <CommentComposer quoted="" onCancel={() => setComposerOpen(false)} onSubmit={submitTopLevel} />
        </div>
      )}
    </div>
  );
}

function CommentBody({
  comment,
  canDelete,
  onDelete,
}: {
  comment: PasteComment;
  canDelete: boolean;
  onDelete: () => void;
}) {
  return (
    <div className="group/comment">
      <p className="flex items-baseline gap-2 text-[12px] text-muted">
        <span className="font-medium text-ink">{comment.author_name || "Anonymous"}</span>
        {timeAgo(comment.created_at)}
        {canDelete && (
          <button
            type="button"
            onClick={onDelete}
            aria-label="Delete comment"
            className="ml-auto text-[12px] text-muted opacity-0 transition hover:text-red-600 group-hover/comment:opacity-100"
          >
            Delete
          </button>
        )}
      </p>
      {comment.quoted_text && (
        <p className="mt-1 truncate border-l-2 border-brand/60 pl-2 text-[12px] italic text-dim">
          {comment.quoted_text}
        </p>
      )}
      <p className="mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
        {comment.body}
      </p>
    </div>
  );
}

function ReplyControl({
  slug,
  parentId,
  onReplyAdded,
}: {
  slug: string;
  parentId: string;
  onReplyAdded: (comment: PasteComment) => void;
}) {
  const [open, setOpen] = useState(false);

  async function submit(input: { author_name: string; body: string }) {
    const result = await addComment(slug, {
      author_name: input.author_name,
      body: input.body,
      quoted_text: "",
      prefix: "",
      suffix: "",
      parent_id: parentId,
    });
    if (result.status === "error") return result.message;
    onReplyAdded(result.comment as PasteComment);
    setOpen(false);
    return "";
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-2 text-[12px] font-medium text-dim hover:text-ink"
      >
        Reply
      </button>
    );
  }
  return (
    <div className="mt-2">
      <CommentComposer quoted="" placeholder="Reply…" onCancel={() => setOpen(false)} onSubmit={submit} />
    </div>
  );
}

export function CommentComposer({
  quoted,
  placeholder = "Add a comment…",
  onCancel,
  onSubmit,
}: {
  quoted: string;
  placeholder?: string;
  onCancel: () => void;
  onSubmit: (input: { author_name: string; body: string }) => Promise<string>;
}) {
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  // Remember the name across comments in this browser.
  useEffect(() => {
    setName(localStorage.getItem(NAME_KEY) ?? "");
  }, []);

  async function send() {
    if (!body.trim() || sending) return;
    setSending(true);
    if (name.trim()) localStorage.setItem(NAME_KEY, name.trim());
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
        placeholder={placeholder}
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
