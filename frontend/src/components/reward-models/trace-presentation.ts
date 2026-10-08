import type { RmStep } from "@/lib/types";
import { buildRows, rowSteps, type TraceRow } from "./trace-rows";

/** Presentation only: the source IDs, roles and offsets remain immutable. */
export function isContext(step: RmStep): boolean {
  return step.role === "system" || (step.role === "user" && /^\s*(?:# AGENTS\.md instructions\b|<(?:environment_context|skills_instructions|INSTRUCTIONS)>)/.test(step.content));
}

export function contextTitle(step: RmStep): string {
  if (/AGENTS\.md/.test(step.content.slice(0, 100))) return "Repository instructions";
  if (/skills_instructions/.test(step.content.slice(0, 100))) return "Skills and instructions";
  if (/environment_context/.test(step.content.slice(0, 100))) return "Environment";
  return "System instructions";
}

export function presentTrace(steps: RmStep[]) {
  const context = steps.filter(isContext);
  const rows = buildRows(steps.filter((step) => !isContext(step)));
  const numberById = new Map<string, number>();
  rows.forEach((row, index) => rowSteps(row).forEach((step) => numberById.set(step.id, index + 1)));
  const mapSteps = rows.map((row, index) => ({ ...rowSteps(row)[0], index }));
  const commentSteps = steps.map((step) => ({ ...step, index: (numberById.get(step.id) ?? 0) - 1 }));
  return { context, rows, numberById, mapSteps, commentSteps };
}

/** Hide known transport envelopes, never arbitrary XML/code the user is discussing. */
export function envelopeRanges(content: string): { start: number; end: number }[] {
  const ranges: { start: number; end: number }[] = [];
  const tags = /<\/?(?:skills_instructions|environment_context|INSTRUCTIONS|multi_agent_role|multi_agent_mode|permissions_instructions|collaboration_mode|send_user_message_question_reply)\b[^>]*>/g;
  for (const match of content.matchAll(tags)) ranges.push({ start: match.index, end: match.index + match[0].length });
  return ranges;
}

export function readableExcerpt(content: string, max = 150): string {
  let text = content;
  const reply = content.match(/<send_user_message_question_reply>\s*([\s\S]*?)\s*<\/send_user_message_question_reply>/);
  if (reply) {
    try { text = (JSON.parse(reply[1]) as { answer: string }[]).map((item) => item.answer).join(" "); } catch { /* Keep the recorded text if malformed. */ }
  }
  if (text === content) for (const range of envelopeRanges(content).reverse()) text = text.slice(0, range.start) + text.slice(range.end);
  text = text.replace(/<image\b[^>]*>[\s\S]*?<\/image>/g, " ").replace(/\[input_image\]|\[Image #\d+\]/g, " ");
  text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/https?:\/\/\S+/g, "");
  text = text.replace(/[#*`]/g, "").replace(/\s+/g, " ").trim();
  return text.length > max ? text.slice(0, max).trimEnd() + "…" : text;
}

export function rowHead(row: TraceRow): RmStep { return rowSteps(row)[0]; }
