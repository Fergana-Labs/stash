import type { RmStep } from "@/lib/types";
import type { ComposerTarget } from "./AnnotationComposer";
import { quoteFromOffsets } from "./rm-text";
import { domSourceOffset } from "./source-anchors";

/** Quote only message content, excluding the headings and controls between messages. */
export function selectedCommentTarget(canvas: HTMLElement, selection: Selection | null, steps: RmStep[]): ComposerTarget | null {
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const range = selection.getRangeAt(0);
  if (!canvas.contains(range.startContainer) || !canvas.contains(range.endContainer)) return null;
  const offsets = new Map<string, { start: number; end: number }>();
  for (const content of canvas.querySelectorAll<HTMLElement>("[data-step-content]")) {
    if (!range.intersectsNode(content)) continue;
    const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      if (!range.intersectsNode(node)) continue;
      const part = document.createRange();
      part.selectNodeContents(node);
      if (part.compareBoundaryPoints(Range.START_TO_START, range) < 0) part.setStart(range.startContainer, range.startOffset);
      if (part.compareBoundaryPoints(Range.END_TO_END, range) > 0) part.setEnd(range.endContainer, range.endOffset);
      if (part.collapsed || !part.toString().trim()) continue;
      const start = domSourceOffset(part.startContainer, part.startOffset);
      const end = domSourceOffset(part.endContainer, part.endOffset);
      if (start === null || end === null || end <= start) continue;
      const id = content.dataset.stepContent!;
      const previous = offsets.get(id);
      offsets.set(id, { start: Math.min(previous?.start ?? start, start), end: Math.max(previous?.end ?? end, end) });
    }
  }
  const segments = steps.flatMap((step) => {
    const span = offsets.get(step.id);
    return span ? [{ step_id: step.id, ...quoteFromOffsets(step.content, span.start, span.end) }] : [];
  });
  if (!segments.length) return null;
  if (segments.length === 1) {
    const { step_id, ...quote } = segments[0];
    return { stepId: step_id, quote };
  }
  return { stepId: null, quote: { text: segments.map((segment) => segment.text).join("\n\n"), prefix: "", suffix: "", segments } };
}
