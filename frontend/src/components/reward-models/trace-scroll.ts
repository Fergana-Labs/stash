import { conversationExcerpt, conversationMarkers, type ConversationMarker } from "@/components/ConversationScrollRail";
import { isThinking, rowSteps, toolLabel, toolSummary, type TraceRow } from "./trace-rows";

export function traceScrollMarkers(rows: TraceRow[]): ConversationMarker[] {
  // Thinking steps remain readable in the trace, but do not stand in for the
  // assistant's response when previewing an exchange.
  const exchanges = conversationMarkers(rows
    .filter((row) => row.kind === "prompt" || (row.kind === "assistant" && !isThinking(row.step)))
    .map((row) => {
      const step = rowSteps(row)[0];
      return { targetId: `step-${step.id}`, role: step.role, content: step.content };
    }));
  if (exchanges.length > 1) return exchanges;

  // A single-request trace can still contain hundreds of actions. In that case
  // (and in Tools view), provide destinations for the individual visible rows.
  const exchangeById = new Map(exchanges.map((exchange) => [exchange.targetId, exchange]));
  return rows.map((row) => {
    const step = rowSteps(row)[0];
    const targetId = `step-${step.id}`;
    const exchange = exchangeById.get(targetId);
    return {
      targetId,
      title: exchange?.title ?? (row.kind === "tool" ? toolLabel(step.tool_name) : row.kind === "prompt" ? "User" : row.kind === "assistant" ? isThinking(step) ? "Thinking" : "Assistant" : "System"),
      preview: exchange?.preview ?? conversationExcerpt(toolSummary(step.tool_input) || step.content),
      label: `Step ${step.index + 1}`,
      emphasis: row.kind === "prompt",
    };
  });
}

export function visibleStepElement(container: HTMLElement, navigation: HTMLElement): HTMLElement | null {
  const boundary = Math.max(container.getBoundingClientRect().top, navigation.getBoundingClientRect().bottom) + 12;
  const elements = [...container.querySelectorAll<HTMLElement>('[id^="step-"]')];
  // The last row may be too short to reach the top beneath the sticky graph.
  const atBottom = container.scrollHeight > container.clientHeight
    && container.scrollHeight - container.scrollTop - container.clientHeight <= 1;
  if (atBottom) elements.reverse();
  let current: HTMLElement | null = null;
  for (const element of elements) {
    if (element.getClientRects().length === 0) continue;
    if (atBottom) return element;
    // Use row starts, not the bottom of a parent tool row that also wraps its result.
    // The selected step lands exactly at this boundary after a minimap jump.
    if (element.getBoundingClientRect().top <= boundary + 1) current = element;
    else return current ?? element;
  }
  return current;
}
