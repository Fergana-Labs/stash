import type { RmStep } from "@/lib/types";
import type { LabelTone } from "./step-labels";

/**
 * A rubric score attached to a step at import time (`step.metadata.reward`),
 * with everything needed to explain it: the rubric's lookup for the step's
 * label, the grader's pick, and the share of later answers pushed back onto it.
 */
export interface StepReward {
  /** The rubric's points for the label alone. */
  base: number;
  baseParts: { text: string; value: number }[];
  grade: {
    rubric: string;
    /** Who graded it, e.g. the model's name. */
    grader: string;
    question: string;
    short: string;
    text: string;
    /** Probability-weighted value actually applied. */
    value: number;
    probability: number | null;
    /** "adjust" adds to the base; "replace" stands in for the base's last part. */
    mode: "adjust" | "replace";
  } | null;
  /** The step's own score after grading. */
  score: number;
  shared: { from: string; verdict: string; value: number }[];
  sharedTotal: number;
  /** `score` plus `sharedTotal`. */
  total: number;
  isAnswer: boolean;
}

export interface TaskScore {
  task: string;
  score: number;
  rubricOnly: number;
  answer: number | null;
  costs: number;
  hasAnswer: boolean;
}

export interface RubricSummary {
  score: number | null;
  episodes: TaskScore[];
  signals: { rejections: number; confirmations: number; tool_errors: number; answers: number };
}

/** One readable piece of a step's score. */
export interface ScorePart {
  text: string;
  /** Shown signed; absent for a part that was replaced by the grader. */
  value?: number;
  /** The rubric's value that the grader replaced, shown struck through. */
  replaced?: number;
  tone: LabelTone;
  title?: string;
  targetChunk?: string;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function stepReward(step: RmStep): StepReward | null {
  const raw = step.metadata?.reward;
  if (typeof raw !== "object" || raw === null) return null;
  const r = raw as Record<string, unknown>;
  const base = num(r.base);
  const score = num(r.score);
  const total = num(r.total);
  if (base === null || score === null || total === null) return null;

  const g = typeof r.jev === "object" && r.jev !== null ? (r.jev as Record<string, unknown>) : null;
  const gradeValue = g ? num(g.value) : null;
  return {
    base,
    baseParts: (Array.isArray(r.base_parts) ? r.base_parts : []).flatMap((p) => {
      const part = p as Record<string, unknown>;
      const value = num(part.value);
      return value === null ? [] : [{ text: str(part.text), value }];
    }),
    grade: g && gradeValue !== null
      ? {
          rubric: str(g.rubric),
          grader: str(g.grader) || "the grader",
          question: str(g.question),
          short: str(g.short),
          text: str(g.text),
          value: gradeValue,
          probability: num(g.probability),
          mode: g.mode === "adjust" ? "adjust" : "replace",
        }
      : null,
    score,
    shared: (Array.isArray(r.shared) ? r.shared : []).flatMap((s) => {
      const item = s as Record<string, unknown>;
      const value = num(item.value);
      return value === null ? [] : [{ from: str(item.from), verdict: str(item.verdict), value }];
    }),
    sharedTotal: num(r.shared_total) ?? 0,
    total,
    isAnswer: r.is_answer === true,
  };
}

export function rubricSummary(value: unknown): RubricSummary | null {
  if (typeof value !== "object" || value === null) return null;
  const v = value as Record<string, unknown>;
  if (!Array.isArray(v.episodes)) return null;
  const signals = (typeof v.signals === "object" && v.signals !== null ? v.signals : {}) as Record<string, unknown>;
  return {
    score: num(v.score),
    episodes: v.episodes.flatMap((e) => {
      const ep = e as Record<string, unknown>;
      const score = num(ep.score);
      if (score === null) return [];
      return [{ task: str(ep.task), score, rubricOnly: num(ep.rubric_b_only) ?? score, answer: num(ep.answer), costs: num(ep.costs) ?? 0, hasAnswer: ep.has_answer === true }];
    }),
    signals: {
      rejections: num(signals.rejections) ?? 0,
      confirmations: num(signals.confirmations) ?? 0,
      tool_errors: num(signals.tool_errors) ?? 0,
      answers: num(signals.answers) ?? 0,
    },
  };
}

/** Two decimals with an explicit sign: +0.30, −0.05, 0.00. */
export function signed(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  if (rounded === 0) return "0.00";
  return `${rounded > 0 ? "+" : "−"}${Math.abs(rounded).toFixed(2)}`;
}

export function scoreTone(value: number): LabelTone {
  if (value >= 0.005) return "good";
  if (value <= -0.095) return "bad";
  if (value <= -0.005) return "warn";
  return "neutral";
}

const VERDICT_PHRASE: Record<string, string> = {
  confirmed: "that the user confirmed",
  implicit_positive: "that the user accepted",
  partial: "that the user called partly right",
  rejected: "that the user rejected",
};

/** The step's score as readable pieces, in the order they were applied. */
export function scoreParts(reward: StepReward, stepNumberOf: (chunk: string) => number | null): ScorePart[] {
  const parts: ScorePart[] = [];
  const grade = reward.grade;
  const replaceIndex = grade?.mode === "replace" ? reward.baseParts.length - 1 : -1;

  reward.baseParts.forEach((part, index) => {
    if (index === replaceIndex) {
      parts.push({ text: part.text, replaced: part.value, tone: "neutral", title: "The fixed points every step with this label starts from. The quality check below takes its place." });
    } else {
      parts.push({ text: part.text, value: part.value, tone: "neutral", title: "Fixed points from the rubric: every step with this label gets the same." });
    }
  });

  if (grade) {
    const sure = grade.probability === null ? "" : `\n\nThe grading model was ${Math.round(grade.probability * 100)}% sure of this option; the points blend all the options by how likely each is, which is why they are not a round number.`;
    parts.push({
      text: `Quality check: ${grade.short}`,
      value: grade.value,
      tone: "info",
      title: `Question asked about this step:\n${grade.question}\n\nOption picked:\n“${grade.text}”\n\n${grade.mode === "adjust" ? "These points are added to the standard cost above." : "These points take the place of the standard points above."}${sure}`,
    });
  }

  // Shares that round to nothing are counted on one line instead of listed.
  const tiny = reward.shared.filter((share) => Math.abs(share.value) < 0.005);
  for (const share of reward.shared) {
    if (tiny.includes(share)) continue;
    const step = stepNumberOf(share.from);
    parts.push({
      text: `${share.value < 0 ? "Blame" : "Credit"} from the answer${step === null ? "" : ` in step ${step}`} ${VERDICT_PHRASE[share.verdict] ?? "that the user reacted to"}`,
      value: share.value,
      tone: share.value < 0 ? "bad" : "good",
      title: `This step helped lead to that answer, so it takes a share of the answer's points. Steps closer to the answer take a bigger share.${step === null ? "" : "\n\nClick to jump to that answer."}`,
      targetChunk: share.from,
    });
  }
  if (tiny.length > 0) {
    parts.push({
      text: `${tiny.length} more distant ${tiny.length === 1 ? "answer" : "answers"}, each worth less than 0.01 here`,
      value: tiny.reduce((sum, share) => sum + share.value, 0),
      tone: "neutral",
      title: "Answers many steps away from this one pass on only a sliver of their points.",
    });
  }
  return parts;
}
