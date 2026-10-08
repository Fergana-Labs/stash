import type { RmStep } from "@/lib/types";
import type { LabelChip, TraceLabels } from "./step-labels";
import { stepReward, type TaskScore } from "./step-rewards";
import { firstLine, rowSteps, type TraceRow } from "./trace-rows";

/**
 * A trace as nested units, each small enough to read at a glance: tasks (a
 * request and everything done for it), turns inside a task (one user message
 * and the agent's work until the next one), and the steps inside a turn.
 * Each level carries a one-line summary so it can stay closed until needed.
 */
export interface OutlineTurn {
  key: string;
  /** The user message that opens the turn; null for steps before the first one. */
  prompt: RmStep | null;
  rows: TraceRow[];
  preview: string;
  userChips: LabelChip[];
  /** What the agent did, in a few words: "4 lookups · 1 error · 1 question". */
  work: string;
  /** The answer the turn ended with, if any. */
  answerChips: LabelChip[];
  /** The scores of the turn's steps added up; null when none of them is scored. */
  points: number | null;
}

export interface OutlineTask {
  key: string;
  number: number;
  title: string;
  turns: OutlineTurn[];
  steps: number;
  /** The last answer in the task and how the user reacted to it. */
  answerChips: LabelChip[];
  score: TaskScore | null;
}

function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

function describeWork(rows: TraceRow[], labels: TraceLabels): string {
  let lookups = 0;
  let actions = 0;
  let errors = 0;
  let empty = 0;
  let repeats = 0;
  let questions = 0;
  let messages = 0;
  for (const row of rows) {
    if (row.kind === "prompt" || row.kind === "system") continue;
    const step = rowSteps(row)[0];
    const label = labels.label(step);
    if (label?.type === "clarifying_question") questions++;
    else if (row.kind === "tool") {
      if (label?.effect === "side_effect") actions++;
      else lookups++;
    } else messages++;
    if (label?.result === "error") errors++;
    if (label?.result === "empty") empty++;
    if (label?.duplicate_of) repeats++;
  }
  const parts = [];
  if (lookups) parts.push(plural(lookups, "lookup"));
  if (actions) parts.push(plural(actions, "action"));
  if (questions) parts.push(plural(questions, "question"));
  if (errors) parts.push(plural(errors, "error"));
  if (empty) parts.push(plural(empty, "empty result"));
  if (repeats) parts.push(plural(repeats, "repeat"));
  if (parts.length === 0 && messages) parts.push(plural(messages, "message"));
  return parts.join(" · ");
}

export function buildOutline(rows: TraceRow[], labels: TraceLabels, scores: TaskScore[]): OutlineTask[] {
  const tasks: OutlineTask[] = [];
  const scoreByTask = new Map(scores.map((score) => [score.task, score]));
  let taskId: string | null = null;
  let turn: OutlineTurn | null = null;

  function openTask(id: string, title: string) {
    taskId = id;
    turn = null;
    tasks.push({ key: `task-${id}`, number: tasks.length + 1, title, turns: [], steps: 0, answerChips: [], score: scoreByTask.get(id) ?? null });
  }

  for (const row of rows) {
    const head = rowSteps(row)[0];
    const label = labels.label(head);
    const rowTask = label?.task_id ?? taskId ?? "t1";
    if (tasks.length === 0 || (label?.task_id && label.task_id !== taskId)) {
      openTask(rowTask, row.kind === "prompt" ? firstLine(head.content, 110) : "");
    }
    const task = tasks.at(-1)!;
    // A user message opens a turn, unless it is the double-logged copy of the one before it.
    const lastRow: TraceRow | undefined = turn?.rows.at(-1);
    const repeated = row.kind === "prompt" && lastRow?.kind === "prompt" && lastRow.step.content === head.content;
    if (turn === null || (row.kind === "prompt" && !repeated)) {
      turn = {
        key: `${task.key}-turn-${task.turns.length + 1}`,
        prompt: row.kind === "prompt" ? head : null,
        rows: [],
        preview: row.kind === "prompt" ? firstLine(head.content, 110) : "Before the first message",
        userChips: row.kind === "prompt" ? labels.chips(head) : [],
        work: "",
        answerChips: [],
        points: null,
      };
      task.turns.push(turn);
      if (task.title === "" && row.kind === "prompt") task.title = turn.preview;
    }
    turn.rows.push(row);
    const reward = stepReward(head);
    if (reward) turn.points = (turn.points ?? 0) + reward.score;
    task.steps += rowSteps(row).length;
    if (label?.is_output) {
      turn.answerChips = labels.chips(head).filter((chip) => chip.tone !== "neutral" || chip.targetStepId !== undefined);
      task.answerChips = turn.answerChips;
    }
  }
  for (const task of tasks) {
    for (const t of task.turns) t.work = describeWork(t.rows, labels);
    if (task.title === "") task.title = "Untitled task";
  }
  return tasks;
}

/** The task and turn that hold a step, for opening them before scrolling to it. */
export function outlinePath(tasks: OutlineTask[], stepId: string): string[] {
  for (const task of tasks) {
    for (const turn of task.turns) {
      if (turn.rows.some((row) => rowSteps(row).some((step) => step.id === stepId))) return [task.key, turn.key];
    }
  }
  return [];
}

/**
 * What starts open: a single task opens so its turns show, and a trace with
 * only a turn or two opens fully. Anything larger starts as a list of
 * one-line summaries.
 */
export function defaultOpen(tasks: OutlineTask[]): Set<string> {
  const open = new Set<string>();
  const turns = tasks.reduce((sum, task) => sum + task.turns.length, 0);
  if (tasks.length <= 2) for (const task of tasks) open.add(task.key);
  if (turns <= 2) for (const task of tasks) for (const turn of task.turns) open.add(turn.key);
  return open;
}
