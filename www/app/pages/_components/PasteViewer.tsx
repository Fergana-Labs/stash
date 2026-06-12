"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import HtmlFrame, { type HtmlSelectionInfo } from "./HtmlFrame";
import MarkdownView from "./MarkdownView";
import { addComment } from "../actions";
import { timeAgo } from "../_lib/time";
import type { Paste, PasteComment } from "../_lib/paste";

const ANCHOR_CONTEXT_CHARS = 32;

// The interactive read view: renders the page and carries the app-style
// comment flow — select text, a Comment pill appears, a popover composer
// posts the comment anchored to the quoted selection. Anchors are stored
// as quoted text + context (never written into the page content, which
// stays token-protected), and threads render below the page.
export default function PasteViewer({
  paste,
  initialComments,
}: {
  paste: Paste;
  initialComments: PasteComment[];
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [comments, setComments] = useState(initialComments);
  const [selection, setSelection] = useState<HtmlSelectionInfo | null>(null);
  // The composer snapshot. Anchor fields are captured at pill-click time —
  // focusing the composer's textarea collapses the document selection, so
  // reading the live selection at submit would lose the quote.
  const [composer, setComposer] = useState<{
    top: number;
    left: number;
    quoted_text: string;
    prefix: string;
    suffix: string;
  } | null>(null);
  const [generalOpen, setGeneralOpen] = useState(false);

  const isHtml = paste.content_type === "html";

  // Markdown selections happen in our own DOM — same quoted/prefix/suffix
  // capture the iframe bootstrap does for HTML pages.
  useEffect(() => {
    if (isHtml) return;
    function onSelectionChange() {
      const wrap = wrapRef.current;
      const sel = window.getSelection();
      if (!wrap || !sel || sel.rangeCount === 0 || sel.isCollapsed) {
        setSelection(null);
        return;
      }
      const range = sel.getRangeAt(0);
      if (!wrap.contains(range.commonAncestorContainer)) {
        setSelection(null);
        return;
      }
      const text = sel.toString();
      if (!text.trim()) {
        setSelection(null);
        return;
      }
      const rects = range.getClientRects();
      const last = rects[rects.length - 1] ?? range.getBoundingClientRect();
      const wrapRect = wrap.getBoundingClientRect();
      const full = wrap.innerText;
      const idx = full.indexOf(text);
      setSelection({
        quoted_text: text,
        prefix: idx >= 0 ? full.slice(Math.max(0, idx - ANCHOR_CONTEXT_CHARS), idx) : "",
        suffix: idx >= 0 ? full.slice(idx + text.length, idx + text.length + ANCHOR_CONTEXT_CHARS) : "",
        rect: {
          top: last.top - wrapRect.top,
          left: last.left - wrapRect.left,
          right: last.right - wrapRect.left,
          bottom: last.bottom - wrapRect.top,
        },
      });
    }
    document.addEventListener("selectionchange", onSelectionChange);
    return () => document.removeEventListener("selectionchange", onSelectionChange);
  }, [isHtml]);

  // HTML selections arrive from the iframe in iframe-viewport coords; the
  // iframe fills the wrapper, so they're already wrapper-relative.
  const onFrameSelection = useCallback((info: HtmlSelectionInfo | null) => {
    setSelection(info);
  }, []);

  async function submit(input: { author_name: string; body: string }) {
    const result = await addComment(paste.slug, {
      author_name: input.author_name,
      body: input.body,
      quoted_text: composer?.quoted_text ?? "",
      prefix: composer?.prefix ?? "",
      suffix: composer?.suffix ?? "",
    });
    if (result.status === "error") return result.message;
    setComments((cur) => [...cur, result.comment as PasteComment]);
    setComposer(null);
    setGeneralOpen(false);
    setSelection(null);
    window.getSelection()?.removeAllRanges();
    return "";
  }

  return (
    <div>
      <div ref={wrapRef} className="relative">
        {isHtml ? (
          <div className="overflow-hidden rounded-xl border border-border bg-white">
            <HtmlFrame html={paste.content} title={paste.title} onSelection={onFrameSelection} />
          </div>
        ) : (
          <MarkdownView content={paste.content} />
        )}

        {selection && !composer && (
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() =>
              setComposer({
                top: selection.rect.bottom + 10,
                left: Math.max(8, (selection.rect.left + selection.rect.right) / 2 - 140),
                quoted_text: selection.quoted_text,
                prefix: selection.prefix,
                suffix: selection.suffix,
              })
            }
            className="absolute z-30 inline-flex -translate-x-1/2 -translate-y-full items-center gap-1.5 rounded-full bg-ink px-3 py-1.5 text-[12px] font-medium text-white shadow-[0_6px_20px_-4px_rgba(0,0,0,0.35)] hover:bg-ink/90"
            style={{
              top: selection.rect.top - 8,
              left: (selection.rect.left + selection.rect.right) / 2,
            }}
          >
            <CommentIcon />
            Comment
          </button>
        )}

        {composer && (
          <div className="absolute z-40" style={{ top: composer.top, left: composer.left }}>
            <CommentComposer
              quoted={composer.quoted_text}
              onCancel={() => setComposer(null)}
              onSubmit={submit}
            />
          </div>
        )}
      </div>

      <section className="mx-auto mt-8 max-w-[920px]">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-[17px] font-semibold text-ink">
            Comments{comments.length > 0 && ` (${comments.length})`}
          </h2>
          {!generalOpen && (
            <button
              type="button"
              onClick={() => setGeneralOpen(true)}
              className="text-[13px] font-medium text-dim hover:text-ink"
            >
              Add a comment
            </button>
          )}
        </div>
        {comments.length === 0 && !generalOpen && (
          <p className="mt-2 text-[13.5px] text-muted">
            No comments yet. Select any text on the page to comment on it.
          </p>
        )}
        <ul className="mt-3 space-y-3">
          {comments.map((comment) => (
            <li key={comment.id} className="rounded-lg border border-border bg-surface p-3.5">
              <p className="flex items-baseline gap-2 text-[12.5px] text-muted">
                <span className="font-medium text-ink">
                  {comment.author_name || "Anonymous"}
                </span>
                {timeAgo(comment.created_at)}
              </p>
              {comment.quoted_text && (
                <p className="mt-1.5 truncate border-l-2 border-brand/60 pl-2 text-[12.5px] italic text-dim">
                  {comment.quoted_text}
                </p>
              )}
              <p className="mt-1.5 whitespace-pre-wrap text-[14px] text-foreground">
                {comment.body}
              </p>
            </li>
          ))}
        </ul>
        {generalOpen && (
          <div className="mt-3">
            <CommentComposer quoted="" onCancel={() => setGeneralOpen(false)} onSubmit={submit} />
          </div>
        )}
      </section>
    </div>
  );
}

function CommentComposer({
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
    <div className="w-[280px] rounded-lg border border-border bg-white p-3 shadow-[0_8px_24px_-6px_rgba(0,0,0,0.25)]">
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
        <button
          type="button"
          onClick={onCancel}
          className="text-[13px] text-dim hover:text-ink"
        >
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

function CommentIcon() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}
