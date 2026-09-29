import type { RmAnnotation, RmQuote, RmStep } from "@/lib/types";

// How much surrounding text a quote carries on each side. The prefix and suffix
// pin a quote to one occurrence when the same words appear twice in a step.
export const QUOTE_CONTEXT_CHARS = 32;

export function quoteFromOffsets(content: string, start: number, end: number): RmQuote {
  return {
    text: content.slice(start, end),
    prefix: content.slice(Math.max(0, start - QUOTE_CONTEXT_CHARS), start),
    suffix: content.slice(end, end + QUOTE_CONTEXT_CHARS),
  };
}

export interface TextRange {
  start: number;
  end: number;
}

/** Where a quote sits in a step's content, or null when the anchored text is not there. */
export function locateQuote(content: string, quote: RmQuote): TextRange | null {
  const anchored = quote.prefix + quote.text + quote.suffix;
  const at = content.indexOf(anchored);
  if (at === -1) return null;
  const start = at + quote.prefix.length;
  return { start, end: start + quote.text.length };
}

export interface Segment {
  text: string;
  /** Ids of every highlight covering this piece of text; empty = plain text. */
  ids: string[];
}

/** Splits content at every highlight boundary so overlapping highlights render as flat spans. */
export function buildSegments(content: string, highlights: (TextRange & { id: string })[]): Segment[] {
  const cuts = new Set<number>([0, content.length]);
  for (const h of highlights) {
    cuts.add(h.start);
    cuts.add(h.end);
  }
  const points = [...cuts].sort((a, b) => a - b);

  const segments: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const start = points[i];
    const end = points[i + 1];
    if (start === end) continue;
    const ids = highlights.filter((h) => h.start <= start && h.end >= end).map((h) => h.id);
    segments.push({ text: content.slice(start, end), ids });
  }
  return segments;
}

/** Annotations in reading order: trace-level first, then by step, then by position in the step. */
export function sortAnnotations(annotations: RmAnnotation[], steps: RmStep[]): RmAnnotation[] {
  const stepById = new Map(steps.map((s) => [s.id, s]));

  function position(a: RmAnnotation): [number, number] {
    if (a.step_id === null) return [-1, 0];
    const step = stepById.get(a.step_id);
    if (!step) throw new Error(`Annotation ${a.id} points at unknown step ${a.step_id}`);
    if (!a.quote) return [step.index, -1];
    const range = locateQuote(step.content, a.quote);
    return [step.index, range ? range.start : -1];
  }

  return [...annotations].sort((a, b) => {
    const [stepA, offsetA] = position(a);
    const [stepB, offsetB] = position(b);
    if (stepA !== stepB) return stepA - stepB;
    if (offsetA !== offsetB) return offsetA - offsetB;
    return a.created_at.localeCompare(b.created_at);
  });
}

/** First non-empty line of a SKILL.md body, skipping the YAML frontmatter. */
export function skillFirstLine(skill: string): string {
  const match = skill.match(/^---\n[\s\S]*?\n---\n/);
  if (!match) throw new Error("SKILL.md is missing its --- frontmatter block");
  const body = skill.slice(match[0].length);
  const line = body.split("\n").find((l) => l.trim() !== "");
  return line === undefined ? "" : line.trim();
}

export type DiffLine = { kind: "same" | "add" | "del"; text: string };

/** Line diff via longest common subsequence. Skills are short, so O(n·m) is fine. */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }

  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      lines.push({ kind: "same", text: a[i] });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      lines.push({ kind: "del", text: a[i] });
      i++;
    } else {
      lines.push({ kind: "add", text: b[j] });
      j++;
    }
  }
  for (; i < a.length; i++) lines.push({ kind: "del", text: a[i] });
  for (; j < b.length; j++) lines.push({ kind: "add", text: b[j] });
  return lines;
}

export function formatScore(score: number): string {
  return score.toFixed(3);
}

export function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

export function relativeTime(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 86400 * 7) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function errorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

/** The line that says what went wrong: the last non-empty line of a worker log tail. */
export function errorSummary(log: string): string {
  const lines = log.split("\n").map((line) => line.trim()).filter(Boolean);
  if (lines.length === 0) throw new Error("errorSummary: empty error text");
  return lines[lines.length - 1];
}
