// Design from Priyadarshan's trace viewer (projects/trace_viewer)
"use client";

import { Fragment, type MouseEvent, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import type { RmTraceImage } from "@/lib/types";
import { buildSegments, type Segment } from "./rm-text";
import { rehypeSourceAnchors, type Highlight } from "./source-anchors";
import { toolOutputRuns } from "./tool-output";
import TraceInlineImage from "./TraceInlineImage";
import styles from "./TraceMarkdown.module.css";

/**
 * A step's content, rendered as markdown or as plain monospace output, with
 * quoted spans highlighted. `data-step-content` marks the root the selection
 * handler reads; every mapped text run carries its source offset.
 */
export default function AnchoredText({
  stepId,
  content,
  images = [],
  markdown,
  highlights,
  onSelectAnnotation,
  className,
}: {
  stepId: string;
  content: string;
  images?: RmTraceImage[];
  markdown: boolean;
  highlights: Highlight[];
  onSelectAnnotation: (ids: string[]) => void;
  className?: string;
}) {
  function onClick(e: MouseEvent) {
    const mark = (e.target as HTMLElement).closest<HTMLElement>("mark[data-ids]");
    if (mark) onSelectAnnotation(mark.dataset.ids!.split(" "));
  }

  function renderContent(text: string, sourceOffset: number) {
    if (markdown) return <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[[rehypeSourceAnchors, { source: text, highlights, sourceOffset }]]}>
      {text}
    </ReactMarkdown>;
    const segments = toolOutputRuns(text).flatMap<Segment & { offset: number | null }>((run) => {
      if (run.offset === null) return [{ text: run.text, ids: [], offset: null }];
      const start = run.offset + sourceOffset;
      const local = highlights
        .filter((h) => h.end > start && h.start < start + run.text.length)
        .map((h) => ({ ...h, start: Math.max(0, h.start - start), end: Math.min(run.text.length, h.end - start) }));
      let offset = start;
      return buildSegments(run.text, local).map((segment) => {
        const mapped = { ...segment, offset };
        offset += segment.text.length;
        return mapped;
      });
    });
    const classById = new Map(highlights.map((h) => [h.id, h.className]));
    return segments.map((segment, i) =>
          segment.ids.length === 0 ? (
            <span key={i} data-o={segment.offset === null ? undefined : segment.offset}>
              {segment.text}
            </span>
          ) : (
            <mark key={i} data-o={segment.offset} data-ids={segment.ids.join(" ")} className={classById.get(segment.ids[0])}>
              {segment.text}
            </mark>
          ),
        );
  }

  const parts: ReactNode[] = [];
  let cursor = 0;
  for (const image of [...images].sort((a, b) => a.start - b.start)) {
    if (image.start < cursor || image.end <= image.start || image.end > content.length) continue;
    parts.push(<Fragment key={`text-${cursor}`}>{renderContent(content.slice(cursor, image.start), cursor)}</Fragment>);
    parts.push(<TraceInlineImage key={image.id} image={image} />);
    cursor = image.end;
  }
  parts.push(<Fragment key={`text-${cursor}`}>{renderContent(content.slice(cursor), cursor)}</Fragment>);
  return (
    <div data-step-content={stepId} onClick={onClick} className={cn(markdown ? styles.prose : styles.out, className)}>
      {parts}
    </div>
  );
}
