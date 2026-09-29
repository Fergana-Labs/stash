import type { Element, ElementContent, Root, RootContent, Text as HastText } from "hast";
import { buildSegments, type TextRange } from "./rm-text";

/**
 * Quotes are stored as offsets into a step's raw content, but assistant and
 * user steps render as markdown, where the text on screen isn't the source
 * (`**bold**` shows as "bold"). This rehype plugin wraps every rendered text
 * run that maps back to the source in <span data-o="<source offset>">, and
 * wraps highlighted runs in <mark data-ids> instead, so both selecting and
 * highlighting work in source offsets. Text that can't be mapped (an HTML
 * entity like &amp;) renders plainly and can't be selected for a quote.
 */

export interface Highlight extends TextRange {
  id: string;
  className: string;
}

type Position = { start: number; end: number };

function positionOf(node: { position?: { start: { offset?: number }; end: { offset?: number } } }): Position | null {
  const start = node.position?.start.offset;
  const end = node.position?.end.offset;
  if (start === undefined || end === undefined) return null;
  return { start, end };
}

/** Source offset of a rendered text run, searched within its own position or its nearest positioned ancestor's. */
export function sourceOffsetOfText(source: string, value: string, window: Position | null): number | null {
  if (window === null || value.trim() === "") return null;
  const at = source.slice(window.start, window.end).indexOf(value);
  return at === -1 ? null : window.start + at;
}

function anchoredRuns(value: string, offset: number, highlights: Highlight[]): ElementContent[] {
  const local = highlights
    .filter((h) => h.end > offset && h.start < offset + value.length)
    .map((h) => ({ id: h.id, start: Math.max(0, h.start - offset), end: Math.min(value.length, h.end - offset) }));
  const byId = new Map(highlights.map((h) => [h.id, h]));

  let cursor = 0;
  return buildSegments(value, local).map((segment) => {
    const at = offset + cursor;
    cursor += segment.text.length;
    const text: HastText = { type: "text", value: segment.text };
    if (segment.ids.length === 0) {
      return { type: "element", tagName: "span", properties: { dataO: at }, children: [text] };
    }
    return {
      type: "element",
      tagName: "mark",
      properties: { dataO: at, dataIds: segment.ids.join(" "), className: byId.get(segment.ids[0])!.className },
      children: [text],
    };
  });
}

function transform(children: RootContent[], source: string, highlights: Highlight[], window: Position | null): RootContent[] {
  return children.flatMap((child): RootContent[] => {
    if (child.type === "text") {
      const offset = sourceOffsetOfText(source, child.value, positionOf(child) ?? window);
      return offset === null ? [child] : anchoredRuns(child.value, offset, highlights);
    }
    if (child.type === "element") {
      const element: Element = child;
      const next = transform(element.children, source, highlights, positionOf(element) ?? window) as ElementContent[];
      return [{ ...element, children: next }];
    }
    return [child];
  });
}

export function rehypeSourceAnchors(options: { source: string; highlights: Highlight[] }) {
  return (tree: Root) => {
    tree.children = transform(tree.children, options.source, options.highlights, null);
  };
}

/** Source offset of a DOM selection boundary inside anchored content, or null when it falls on unmapped text. */
export function domSourceOffset(container: Node, offset: number): number | null {
  if (container.nodeType === Node.TEXT_NODE) {
    const holder = container.parentElement?.closest<HTMLElement>("[data-o]");
    if (!holder) return null;
    return Number(holder.dataset.o) + offset;
  }
  const next = container.childNodes[offset];
  if (next) {
    const text = firstText(next);
    return text ? domSourceOffset(text, 0) : null;
  }
  const previous = container.childNodes[offset - 1];
  const text = previous ? lastText(previous) : null;
  return text ? domSourceOffset(text, text.data.length) : null;
}

function firstText(node: Node): Text | null {
  if (node.nodeType === Node.TEXT_NODE) return node as Text;
  for (const child of Array.from(node.childNodes)) {
    const found = firstText(child);
    if (found) return found;
  }
  return null;
}

function lastText(node: Node): Text | null {
  if (node.nodeType === Node.TEXT_NODE) return node as Text;
  const children = Array.from(node.childNodes);
  for (let i = children.length - 1; i >= 0; i--) {
    const found = lastText(children[i]);
    if (found) return found;
  }
  return null;
}
