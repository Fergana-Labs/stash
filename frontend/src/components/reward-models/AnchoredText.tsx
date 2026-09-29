// Design from Priyadarshan's trace viewer (projects/trace_viewer)
"use client";

import type { MouseEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { buildSegments } from "./rm-text";
import { rehypeSourceAnchors, type Highlight } from "./source-anchors";
import styles from "./TraceMarkdown.module.css";

/**
 * A step's content, rendered as markdown or as plain monospace output, with
 * quoted spans highlighted. `data-step-content` marks the root the selection
 * handler reads; every mapped text run carries its source offset.
 */
export default function AnchoredText({
  stepId,
  content,
  markdown,
  highlights,
  onSelectAnnotation,
  className,
}: {
  stepId: string;
  content: string;
  markdown: boolean;
  highlights: Highlight[];
  onSelectAnnotation: (ids: string[]) => void;
  className?: string;
}) {
  function onClick(e: MouseEvent) {
    const mark = (e.target as HTMLElement).closest<HTMLElement>("mark[data-ids]");
    if (mark) onSelectAnnotation(mark.dataset.ids!.split(" "));
  }

  if (!markdown) {
    const segments = buildSegments(content, highlights);
    const starts = segments.map((_, i) => segments.slice(0, i).reduce((sum, s) => sum + s.text.length, 0));
    const classById = new Map(highlights.map((h) => [h.id, h.className]));
    return (
      <div data-step-content={stepId} onClick={onClick} className={cn(styles.out, className)}>
        {segments.map((segment, i) =>
          segment.ids.length === 0 ? (
            <span key={i} data-o={starts[i]}>
              {segment.text}
            </span>
          ) : (
            <mark key={i} data-o={starts[i]} data-ids={segment.ids.join(" ")} className={classById.get(segment.ids[0])}>
              {segment.text}
            </mark>
          ),
        )}
      </div>
    );
  }

  return (
    <div data-step-content={stepId} onClick={onClick} className={cn(styles.prose, className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[[rehypeSourceAnchors, { source: content, highlights }]]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
