"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import CommentsRail, { CommentComposer } from "./CommentsRail";
import HtmlFrame, { type HtmlSelectionInfo } from "./HtmlFrame";
import MarkdownView from "./MarkdownView";
import { addComment } from "../actions";
import type { Paste, PasteComment } from "../_lib/paste";

const ANCHOR_CONTEXT_CHARS = 32;

// The interactive read view: the page on the left, a Google-Docs-style
// comments rail on the right. Selecting text (in the markdown article,
// or inside the sandboxed iframe) surfaces a Comment pill whose popover
// posts a comment anchored to the quoted selection. Anchors are stored
// as quoted text + context — never written into the page content, which
// stays token-protected. The page owner can turn the whole thing off
// for view mode (comments_enabled).
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

  const isHtml = paste.content_type === "html";
  const commentsEnabled = paste.comments_enabled;

  // Markdown selections happen in our own DOM — same quoted/prefix/suffix
  // capture the iframe bootstrap does for HTML pages.
  useEffect(() => {
    if (isHtml || !commentsEnabled) return;
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
        suffix:
          idx >= 0 ? full.slice(idx + text.length, idx + text.length + ANCHOR_CONTEXT_CHARS) : "",
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
  }, [isHtml, commentsEnabled]);

  // HTML selections arrive from the iframe in iframe-viewport coords; the
  // iframe fills the wrapper, so they're already wrapper-relative.
  const onFrameSelection = useCallback(
    (info: HtmlSelectionInfo | null) => {
      if (commentsEnabled) setSelection(info);
    },
    [commentsEnabled],
  );

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
    setSelection(null);
    window.getSelection()?.removeAllRanges();
    return "";
  }

  const content = (
    <div ref={wrapRef} className="relative min-w-0">
      {isHtml ? (
        <div className="overflow-hidden rounded-xl border border-border bg-white">
          <HtmlFrame
            html={paste.content}
            title={paste.title}
            onSelection={commentsEnabled ? onFrameSelection : undefined}
          />
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
  );

  if (!commentsEnabled) return content;

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_280px] lg:gap-7">
      {content}
      <aside className="mt-8 lg:mt-0">
        <div className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-48px)] lg:overflow-y-auto">
          <CommentsRail comments={comments} onSubmit={submit} />
        </div>
      </aside>
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
