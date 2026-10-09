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
import { rehypeTraceSyntax } from "./trace-syntax";
import { envelopeRanges } from "./trace-presentation";
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
    if (!window.getSelection()?.isCollapsed) return;
    const mark = (e.target as HTMLElement).closest<HTMLElement>("mark[data-ids]");
    if (mark) onSelectAnnotation(mark.dataset.ids!.split(" "));
  }

  function renderContent(text: string, sourceOffset: number, asMarkdown = markdown) {
    if (asMarkdown) return <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[[rehypeTraceSyntax, { source: text }], [rehypeSourceAnchors, { source: text, highlights, sourceOffset }]]}>
      {text}
    </ReactMarkdown>;
    const segments = toolOutputRuns(text).flatMap<Segment & { offset: number | null; sourceEnd?: number }>((run) => {
      if (run.offset === null) return [{ text: run.text, ids: [], offset: null }];
      const start = run.offset + sourceOffset;
      if (run.sourceLength !== undefined && run.sourceLength !== run.text.length) {
        return [{ text: run.text, offset: start, sourceEnd: start + run.sourceLength,
          ids: highlights.filter((h) => h.end > start && h.start < start + run.sourceLength!).map((h) => h.id) }];
      }
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
            <span key={i} data-o={segment.offset === null ? undefined : segment.offset} data-source-end={segment.sourceEnd}>
              {segment.text}
            </span>
          ) : (
            <mark key={i} data-o={segment.offset} data-source-end={segment.sourceEnd} data-ids={segment.ids.join(" ")} className={classById.get(segment.ids[0])}>
              {segment.text}
            </mark>
          ),
        );
  }

  const parts: ReactNode[] = [];
  let cursor = 0;
  const replacements: { start: number; end: number; image?: RmTraceImage; element?: ReactNode }[] = images.map((image) => ({ ...image, image }));
  for (const reply of content.matchAll(/<send_user_message_question_reply>\s*([\s\S]*?)\s*<\/send_user_message_question_reply>/g)) {
    const bodyStart = reply.index + reply[0].indexOf(reply[1]);
    const fields = [...reply[1].matchAll(/"(question|answer)"\s*:\s*("(?:\\.|[^"\\])*")/g)];
    if (fields.length) replacements.push({ start: reply.index, end: reply.index + reply[0].length,
      element: <div key={`reply-${reply.index}`} className="space-y-2">{fields.map((field) => <div key={field.index} className={field[1] === "question" ? "text-xs text-muted-foreground" : "whitespace-pre-wrap"}>
        {field[1] === "question" && <span>Asked: </span>}{renderContent(field[2], bodyStart + field.index + field[0].indexOf(field[2]), false)}
      </div>)}</div> });
  }
  for (const missing of content.matchAll(/<image\b[^>]*>[\s\S]*?<\/image>/g)) {
    if (!images.some((image) => image.start <= missing.index && image.end >= missing.index + missing[0].length)) replacements.push({ start: missing.index, end: missing.index + missing[0].length,
      element: <p key={`missing-${missing.index}`} className="my-2 text-xs text-muted-foreground">Image wasn’t included in this recording. Sync the original session to restore it.</p> });
  }
  replacements.push(...envelopeRanges(content).filter((range) => !replacements.some((replacement) => range.start < replacement.end && range.end > replacement.start)));
  for (const replacement of replacements.sort((a, b) => a.start - b.start)) {
    const { start, end, image, element } = replacement;
    if (start < cursor || end <= start || end > content.length) continue;
    parts.push(<Fragment key={`text-${cursor}`}>{renderContent(content.slice(cursor, start), cursor)}</Fragment>);
    if (image) parts.push(<TraceInlineImage key={image.id} image={image} />);
    if (element) parts.push(element);
    cursor = end;
  }
  parts.push(<Fragment key={`text-${cursor}`}>{renderContent(content.slice(cursor), cursor)}</Fragment>);
  return (
    <div data-step-content={stepId} onClick={onClick} className={cn(markdown ? styles.prose : styles.out, className)}>
      {parts}
    </div>
  );
}
