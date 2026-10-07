"use client";

/** Preserve unchanged outer lines; show the exact replaced block in order. */
export function changedLines(before: string, after: string): { kind: "same" | "removed" | "added"; text: string }[] {
  if (before === after) return before.split("\n").map((text) => ({ kind: "same", text }));
  const oldLines = before ? before.split("\n") : [];
  const newLines = after ? after.split("\n") : [];
  let start = 0, end = 0;
  while (start < oldLines.length && start < newLines.length && oldLines[start] === newLines[start]) start++;
  while (end < oldLines.length - start && end < newLines.length - start && oldLines[oldLines.length - end - 1] === newLines[newLines.length - end - 1]) end++;
  return [
    ...oldLines.slice(0, start).map((text) => ({ kind: "same" as const, text })),
    ...oldLines.slice(start, oldLines.length - end).map((text) => ({ kind: "removed" as const, text })),
    ...newLines.slice(start, newLines.length - end).map((text) => ({ kind: "added" as const, text })),
    ...oldLines.slice(oldLines.length - end).map((text) => ({ kind: "same" as const, text })),
  ];
}

export default function ContentDiff({ before, after }: { before: string; after: string }) {
  return <details className="rounded-md border border-border"><summary className="cursor-pointer p-3 text-[12px] font-medium">Changes from the previous released version</summary><p className="mx-3 mt-0 text-[11px] text-muted-foreground">− Previous content · + Proposed content</p><pre className="m-0 max-h-96 overflow-auto pb-3 text-[11.5px] leading-relaxed">{changedLines(before, after).map((line, index) => <span key={index} className={`block whitespace-pre-wrap break-words px-3 ${line.kind === "removed" ? "bg-red-500/10 text-red-800 dark:text-red-300" : line.kind === "added" ? "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300" : "text-muted-foreground"}`}>{line.kind === "removed" ? "− " : line.kind === "added" ? "+ " : "  "}{line.text || " "}</span>)}</pre></details>;
}
