import type { RmStep } from "@/lib/types";

/**
 * A rubric label attached to a step at import time (`step.metadata.label`).
 * User steps carry intent / verdict / sentiment; agent steps carry a type and,
 * when they deliver the answer, the output attributes. Ids such as
 * `verdict_target` and `duplicate_of` are chunk ids within the same trace.
 */
export interface StepLabel {
  chunk_id: string;
  task_id: string | null;
  actor: "user" | "agent";
  intent: string | null;
  verdict: string | null;
  verdict_target: string | null;
  sentiment: string | null;
  type: string | null;
  effect: string | null;
  result: string | null;
  duplicate_of: string | null;
  is_output: boolean;
  outcome: string | null;
  stance: string | null;
  coverage: string | null;
  evidence: string | null;
  note: string | null;
}

export type LabelTone = "neutral" | "good" | "bad" | "warn" | "info";

export interface LabelChip {
  text: string;
  tone: LabelTone;
  /** What the label means, shown on hover. */
  title: string;
  /** Clicking the chip jumps to this step. */
  targetStepId?: string;
}

export interface LabelSummaryItem {
  key: string;
  text: string;
  tone: LabelTone;
  /** Steps this count refers to, in trace order. */
  stepIds: string[];
}

export interface TraceLabels {
  /** False when no step in the trace carries a label. */
  present: boolean;
  label: (step: RmStep) => StepLabel | null;
  chips: (step: RmStep) => LabelChip[];
  /** "Task 2" on the step that opens a task, when the trace has more than one. */
  taskHeading: (step: RmStep) => string | null;
  /** The step a chunk id (`a3`, `u2`) refers to. */
  stepForChunk: (chunk: string) => RmStep | null;
  summary: LabelSummaryItem[];
}

function text(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

export function stepLabel(step: RmStep): StepLabel | null {
  const raw = step.metadata?.label;
  if (typeof raw !== "object" || raw === null) return null;
  const l = raw as Record<string, unknown>;
  const chunkId = text(l.chunk_id);
  if (chunkId === null || (l.actor !== "user" && l.actor !== "agent")) return null;
  return {
    chunk_id: chunkId,
    task_id: text(l.task_id),
    actor: l.actor,
    intent: text(l.intent),
    verdict: text(l.verdict),
    verdict_target: text(l.verdict_target),
    sentiment: text(l.sentiment),
    type: text(l.type),
    effect: text(l.effect),
    result: text(l.result),
    duplicate_of: text(l.duplicate_of),
    is_output: l.is_output === true,
    outcome: text(l.outcome),
    stance: text(l.stance),
    coverage: text(l.coverage),
    evidence: text(l.evidence),
    note: text(l.note),
  };
}

function words(value: string): string {
  const spaced = value.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** What the user is doing with a message: [chip text, tone, meaning]. */
const INTENT: Record<string, [string, LabelTone, string]> = {
  new_request: ["New request", "neutral", "The user asks for something new."],
  follow_up: ["Follow-up question", "neutral", "A new question that builds on the agent's previous answer."],
  clarification_answer: ["Answers the agent's question", "neutral", "The user replies to a question the agent asked."],
  added_context: ["Adds context", "neutral", "The user volunteers more information without saying the agent was wrong."],
  correction: ["Corrects the agent", "bad", "The user says or implies the agent was wrong and redirects it. This counts as rejecting the previous answer."],
  requirement_change: ["Changes the request", "warn", "The user changes what they want, without saying the agent was wrong."],
  repeat_request: ["Asks again", "bad", "The user asks for the same thing again. This counts as rejecting the previous answer."],
  acknowledgment: ["Acknowledges", "neutral", "The message adds nothing new, such as “ok” or “thanks”."],
  other: ["Unclear", "neutral", "The labeler could not decide what this message is doing."],
};

/** How the user reacted to an answer: [on the user's message, on the answer, tone, meaning]. */
const VERDICT: Record<string, [string, string, LabelTone, string]> = {
  confirmed: ["Confirms the answer", "Confirmed by the user", "good", "The user explicitly said the answer was right, or acted on it."],
  implicit_positive: ["Accepts the answer", "Accepted by the user", "good", "The user said thanks or moved on without complaint."],
  partial: ["Says the answer is partly right", "Partly right, per the user", "warn", "The user said some parts were right and some were wrong."],
  rejected: ["Rejects the answer", "Rejected by the user", "bad", "The user said the answer was wrong, corrected the agent, or asked for the same thing again."],
};

/** What the agent handed the user: [chip text, tone, meaning]. */
const OUTCOME: Record<string, [string, LabelTone, string]> = {
  answer: ["Answer given", "info", "This step gives the user an answer to their request."],
  partial_answer: ["Partial answer", "warn", "This step answers only some of the items the user asked for."],
  not_found: ["Answer: not found", "warn", "This step tells the user the requested thing could not be found."],
  handoff: ["Handed off", "warn", "This step escalates to a person or declines the request."],
  error: ["Reported a failure", "bad", "This step tells the user about a failure the agent did not recover from."],
};

function withEvidence(meaning: string, label: StepLabel): string {
  const parts = [meaning];
  if (label.evidence) parts.push(`Evidence: “${label.evidence}”`);
  if (label.note) parts.push(`Note: ${label.note}`);
  return parts.join("\n\n");
}

function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function buildTraceLabels(steps: RmStep[], numberOf: (step: RmStep) => number = (step) => step.index + 1): TraceLabels {
  const labels = new Map<string, StepLabel>();
  const stepByChunk = new Map<string, RmStep>();
  for (const step of steps) {
    const label = stepLabel(step);
    if (label === null) continue;
    labels.set(step.id, label);
    stepByChunk.set(label.chunk_id, step);
  }

  // The verdict a user step passes on an output, looked up from the output's side.
  const verdictOn = new Map<string, { verdict: string; from: RmStep }>();
  const taskOpeners = new Map<string, string>();
  const seenTasks = new Set<string>();
  for (const step of steps) {
    const label = labels.get(step.id);
    if (!label) continue;
    if (label.task_id !== null && !seenTasks.has(label.task_id)) {
      seenTasks.add(label.task_id);
      taskOpeners.set(step.id, label.task_id);
    }
    if (label.actor === "user" && label.verdict !== null && label.verdict !== "none" && label.verdict_target !== null) {
      const target = stepByChunk.get(label.verdict_target);
      if (target) verdictOn.set(target.id, { verdict: label.verdict, from: step });
    }
  }

  function chips(step: RmStep): LabelChip[] {
    const label = labels.get(step.id);
    if (!label) return [];
    const out: LabelChip[] = [];

    if (label.actor === "user") {
      if (label.intent) {
        const [name, tone, meaning] = INTENT[label.intent] ?? [words(label.intent), "neutral", "What the user is doing with this message."];
        out.push({ text: name, tone, title: withEvidence(meaning, label) });
      }
      if (label.verdict && label.verdict !== "none") {
        const [onUser, , tone, meaning] = VERDICT[label.verdict] ?? [words(label.verdict), "", "neutral", "The user's reaction to the agent's answer."];
        const target = label.verdict_target ? stepByChunk.get(label.verdict_target) : undefined;
        out.push({
          text: target ? `${onUser} in step ${numberOf(target)}` : onUser,
          tone,
          title: target
            ? `With this message the user reacts to the answer the agent gave in step ${numberOf(target)}. ${meaning}\n\nClick to jump to that answer.`
            : `With this message the user reacts to the agent's previous answer. ${meaning}`,
          targetStepId: target?.id,
        });
      }
      if (label.sentiment === "negative") out.push({ text: "Negative tone", tone: "bad", title: "The user sounds unhappy in this message. Tracked, but it does not change the score." });
      if (label.sentiment === "positive") out.push({ text: "Positive tone", tone: "good", title: "The user sounds pleased in this message. Tracked, but it does not change the score." });
      return out;
    }

    if (label.type === "clarifying_question") out.push({ text: "Question to the user", tone: "info", title: withEvidence("The agent asks the user for information it needs.", label) });
    else if (label.type === "status_update") out.push({ text: "Progress update", tone: "neutral", title: withEvidence("A message to the user that is explicitly not the final answer.", label) });
    else if (label.type === "reasoning") out.push({ text: "Reasoning", tone: "neutral", title: withEvidence("Internal thinking that the user does not see.", label) });
    else if (label.type === "other") out.push({ text: "Unclear", tone: "neutral", title: withEvidence("The labeler could not decide what kind of step this is.", label) });

    if (label.type === "tool_call") {
      // Lookups that returned data are the unremarkable default; only the exceptions get a chip.
      if (label.effect === "side_effect") out.push({ text: "Changes something", tone: "info", title: withEvidence("This tool call creates, changes, sends or records something, instead of only looking something up.", label) });
      if (label.result === "empty") out.push({ text: "Returned nothing useful", tone: "warn", title: withEvidence("The tool ran but came back with no rows, no matches, or an empty list.", label) });
      if (label.result === "error") out.push({ text: "Returned an error", tone: "bad", title: withEvidence("The tool call failed.", label) });
      if (label.duplicate_of) {
        const first = stepByChunk.get(label.duplicate_of);
        out.push({
          text: first ? `Same call as step ${numberOf(first)}` : "Repeats an earlier call",
          tone: "warn",
          title: `The agent called the same tool with exactly the same arguments earlier${first ? ` (step ${numberOf(first)}). Click to jump to it.` : "."}`,
          targetStepId: first?.id,
        });
      }
    }

    if (label.is_output) {
      const [name, tone, meaning] = OUTCOME[label.outcome ?? ""] ?? ["Response to the user", "info", "This step is the agent's response to the user's request."];
      out.push({ text: name, tone, title: withEvidence(meaning, label) });
      if (label.stance === "hedged") out.push({ text: "With caveats", tone: "neutral", title: "The response states its own uncertainty or caveats." });
      if (label.stance === "asserted") out.push({ text: "No caveats", tone: "neutral", title: "The response is stated plainly, without mentioning any uncertainty." });
      const coverage = label.coverage?.match(/^(\d+)\/(\d+)$/);
      if (coverage) out.push({ text: `${coverage[1]} of ${plural(Number(coverage[2]), "item")}`, tone: "neutral", title: `The response addresses ${coverage[1]} of the ${coverage[2]} things the user asked for.` });

      const received = verdictOn.get(step.id);
      if (received) {
        const [, onAnswer, verdictTone, verdictMeaning] = VERDICT[received.verdict] ?? ["", words(received.verdict), "neutral", "The user's reaction to this answer."];
        out.push({
          text: `${onAnswer} in step ${numberOf(received.from)}`,
          tone: verdictTone,
          title: `The user reacted to this answer in step ${numberOf(received.from)}. ${verdictMeaning}\n\nClick to jump to the user's message.`,
          targetStepId: received.from.id,
        });
      }
    }
    return out;
  }

  function ids(match: (label: StepLabel) => boolean): string[] {
    return steps.filter((step) => {
      const label = labels.get(step.id);
      return label !== undefined && match(label);
    }).map((step) => step.id);
  }

  const summary: LabelSummaryItem[] = [];
  function add(key: string, stepIds: string[], one: string, tone: LabelTone, many?: string) {
    if (stepIds.length > 0) summary.push({ key, text: plural(stepIds.length, one, many), tone, stepIds });
  }
  if (seenTasks.size > 1) add("tasks", [...taskOpeners.keys()], "task", "neutral");
  add("outputs", ids((l) => l.is_output), "answer", "info");
  add("confirmed", ids((l) => l.verdict === "confirmed" || l.verdict === "implicit_positive"), "answer accepted", "good", "answers accepted");
  add("rejected", ids((l) => l.verdict === "rejected"), "answer rejected", "bad", "answers rejected");
  add("partial", ids((l) => l.verdict === "partial"), "answer partly right", "warn", "answers partly right");
  add("questions", ids((l) => l.type === "clarifying_question"), "question to the user", "info", "questions to the user");
  add("side-effects", ids((l) => l.type === "tool_call" && l.effect === "side_effect"), "call that changes something", "info", "calls that change something");
  add("empty", ids((l) => l.result === "empty"), "empty result", "warn");
  add("errors", ids((l) => l.result === "error"), "tool error", "bad");
  add("duplicates", ids((l) => l.duplicate_of !== null), "repeated call", "warn");

  return {
    present: labels.size > 0,
    label: (step) => labels.get(step.id) ?? null,
    chips,
    taskHeading: (step) => {
      const task = taskOpeners.get(step.id);
      if (task === undefined || seenTasks.size < 2) return null;
      return `Task ${task.replace(/^t/, "")}`;
    },
    stepForChunk: (chunk) => stepByChunk.get(chunk) ?? null,
    summary,
  };
}
