"use client";

import { useEffect, useState, type RefObject } from "react";

import { CommentComposer } from "./CommentsRail";
import type { HtmlSelectionInfo } from "./HtmlFrame";
import { addComment } from "../actions";
import type { PasteComment } from "../_lib/paste";

const ANCHOR_CONTEXT_CHARS = 32;

// The select-to-comment flow, shared by the read and edit pages: render
// this inside a `relative` content wrapper and it shows a Comment pill
// over any text selection, opening a popover composer that posts the
// comment anchored to the quoted text. Selections come from the wrapper's
// own DOM (markdown article, Tiptap editor) via `listenDom`, or from a
// sandboxed iframe via `frameSelection`.
export default function SelectionCommentLayer({
  slug,
  wrapRef,
  listenDom = false,
  frameSelection = null,
  onCommentAdded,
}: {
  slug: string;
  wrapRef: RefObject<HTMLDivElement | null>;
  listenDom?: boolean;
  frameSelection?: HtmlSelectionInfo | null;
  onCommentAdded: (comment: PasteComment) => void;
}) {
  const [selection, setSelection] = useState<HtmlSelectionInfo | null>(null);
  // Anchor fields are captured at pill-click time — focusing the
  // composer's textarea collapses the document selection, so reading the
  // live selection at submit would lose the quote.
  const [composer, setComposer] = useState<{
    top: number;
    left: number;
    quoted_text: string;
    prefix: string;
    suffix: string;
  } | null>(null);

  useEffect(() => {
    if (!listenDom) return;
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
  }, [listenDom, wrapRef]);

  useEffect(() => {
    if (frameSelection !== undefined && !listenDom) setSelection(frameSelection);
  }, [frameSelection, listenDom]);

  async function submit(input: { author_name: string; body: string }) {
    const result = await addComment(slug, {
      author_name: input.author_name,
      body: input.body,
      quoted_text: composer?.quoted_text ?? "",
      prefix: composer?.prefix ?? "",
      suffix: composer?.suffix ?? "",
    });
    if (result.status === "error") return result.message;
    onCommentAdded(result.comment as PasteComment);
    setComposer(null);
    setSelection(null);
    window.getSelection()?.removeAllRanges();
    return "";
  }

  return (
    <>
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
    </>
  );
}

function CommentIcon() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}
