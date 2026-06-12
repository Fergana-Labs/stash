"use client";

import { useCallback, useRef, useState } from "react";

import CommentsRail from "./CommentsRail";
import HtmlFrame, { type HtmlSelectionInfo } from "./HtmlFrame";
import MarkdownView from "./MarkdownView";
import SelectionCommentLayer from "./SelectionCommentLayer";
import type { Paste, PasteComment } from "../_lib/paste";

// The interactive read view. Selecting text (in the markdown article, or
// inside the sandboxed iframe) surfaces a Comment pill; threads live in a
// Google-Docs-style right rail that only appears once the page has its
// first comment. The page owner can turn commenting off for readers
// entirely (comments_enabled).
export default function PasteViewer({
  paste,
  initialComments,
}: {
  paste: Paste;
  initialComments: PasteComment[];
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [comments, setComments] = useState(initialComments);
  const [frameSelection, setFrameSelection] = useState<HtmlSelectionInfo | null>(null);

  const isHtml = paste.content_type === "html";
  const commentsEnabled = paste.comments_enabled;

  const onFrameSelection = useCallback((info: HtmlSelectionInfo | null) => {
    setFrameSelection(info);
  }, []);

  const addLocal = useCallback((comment: PasteComment) => {
    setComments((cur) => [...cur, comment]);
  }, []);

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
      {commentsEnabled && (
        <SelectionCommentLayer
          slug={paste.slug}
          wrapRef={wrapRef}
          listenDom={!isHtml}
          frameSelection={frameSelection}
          onCommentAdded={addLocal}
        />
      )}
    </div>
  );

  if (!commentsEnabled || comments.length === 0) return content;

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_280px] lg:gap-7">
      {content}
      <aside className="mt-8 lg:mt-0">
        <div className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-48px)] lg:overflow-y-auto">
          <CommentsRail slug={paste.slug} comments={comments} onCommentAdded={addLocal} />
        </div>
      </aside>
    </div>
  );
}
