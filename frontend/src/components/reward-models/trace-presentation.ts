import type { RmStep } from "@/lib/types";
import { buildRows, rowSteps, type TraceRow } from "./trace-rows";

export function presentTrace(steps: RmStep[]) {
  // Every source message stays in chronological order, regardless of role or content.
  const rows = buildRows(steps);
  const numberById = new Map<string, number>();
  rows.forEach((row, index) => rowSteps(row).forEach((step) => numberById.set(step.id, index + 1)));
  const mapSteps = rows.map((row, index) => ({ ...rowSteps(row)[0], index }));
  const commentSteps = steps.map((step) => ({ ...step, index: (numberById.get(step.id) ?? 0) - 1 }));
  return { rows, numberById, mapSteps, commentSteps };
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
