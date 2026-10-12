import type {
  Driver,
  Example,
  Head,
  Item,
  Metrics,
  ModelDetail,
  NewExample,
  OutputLabel,
  OutputType,
  QuestionAblation,
  RubricQuestion,
  Split,
  Version,
} from "@/lib/intuition-api";

/** Pure helpers for the intuition-model UI (no React, no fetching). */

export const MAX_SEEDS = 20;
export const MAX_QUESTIONS = 12;
export const DEFAULT_L2 = 0.005;
export const PREFERENCE_ITEM_LABELS = ["good", "bad"] as const;
export const PAIR_LABELS = ["a", "b"] as const;
const SLUG = /^[a-z0-9][a-z0-9_-]{0,63}$/;

/** The version edits apply to and that the UI describes: the draft when there is one. */
export function workingVersion(detail: ModelDetail): Version | null {
  return detail.draft ?? detail.active;
}

export function isSlug(value: string): boolean {
  return SLUG.test(value);
}

/** "Answers the question?" -> "answers_the_question". */
export function slugify(text: string): string {
  const slug = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
  return slug && /^[a-z0-9]/.test(slug) ? slug : "";
}

/** A slug based on `base` that is not in `taken`. */
export function uniqueSlug(base: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  const root = slugify(base) || "question";
  if (!used.has(root)) return root;
  for (let i = 2; ; i++) {
    const candidate = `${root.slice(0, 60)}_${i}`;
    if (!used.has(candidate)) return candidate;
  }
}

// ── Features ────────────────────────────────────────────────────────────

export interface FeatureInfo {
  feature: string;
  questionId: string;
  question: RubricQuestion | null;
  /** Option key ("warm"), level index as a string ("2"), or null for a yes/no question. */
  option: string | null;
  /** Human label for the option: the option/level description, or "yes" for yes/no. */
  optionLabel: string;
}

/**
 * Map a head feature name to the rubric question it comes from.
 * noul -> "answers_question"; choice -> "tone=warm"; score -> "length=2" (level index).
 */
export function describeFeature(feature: string, rubric: RubricQuestion[]): FeatureInfo {
  const at = feature.indexOf("=");
  const questionId = at === -1 ? feature : feature.slice(0, at);
  const option = at === -1 ? null : feature.slice(at + 1);
  const question = rubric.find((q) => q.id === questionId) ?? null;
  return { feature, questionId, question, option, optionLabel: optionLabel(question, option) };
}

function optionLabel(question: RubricQuestion | null, option: string | null): string {
  if (option === null) return "yes";
  if (!question) return option;
  if (question.type === "score" && Array.isArray(question.criteria)) {
    const level = Number(option);
    const text = question.criteria[level];
    return text ? `${level} · ${text}` : `level ${option}`;
  }
  if (!Array.isArray(question.criteria)) {
    const text = question.criteria[option];
    return text ? `${option} · ${text}` : option;
  }
  return option;
}

export interface FeatureGroup {
  questionId: string;
  question: RubricQuestion | null;
  features: { index: number; info: FeatureInfo }[];
}

/** Feature names grouped by question, in feature order. */
export function groupFeatures(featureNames: string[], rubric: RubricQuestion[]): FeatureGroup[] {
  const groups: FeatureGroup[] = [];
  featureNames.forEach((name, index) => {
    const info = describeFeature(name, rubric);
    const last = groups[groups.length - 1];
    if (last && last.questionId === info.questionId) last.features.push({ index, info });
    else groups.push({ questionId: info.questionId, question: info.question, features: [{ index, info }] });
  });
  return groups;
}

/** Answer keys for a question, in display order, paired with their descriptions. */
export function questionOptions(question: RubricQuestion): { key: string; label: string }[] {
  if (question.type === "noul") return [{ key: "true", label: "yes" }, { key: "false", label: "no" }];
  if (Array.isArray(question.criteria)) return question.criteria.map((text, i) => ({ key: String(i), label: text }));
  return Object.entries(question.criteria).map(([key, text]) => ({ key, label: text ? `${key} · ${text}` : key }));
}

/** P(yes) for a yes/no answer distribution; providers key it "true". */
export function pYes(answer: Record<string, number> | undefined): number | null {
  if (!answer) return null;
  if (typeof answer.true === "number") return answer.true;
  if (typeof answer.yes === "number") return answer.yes;
  if (typeof answer.false === "number") return 1 - answer.false;
  return null;
}

/** Top contributions by absolute value. */
export function topContributions(contributions: Record<string, number> | undefined, n = 8): [string, number][] {
  if (!contributions) return [];
  return Object.entries(contributions)
    .filter(([, v]) => Number.isFinite(v))
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, n);
}

// ── Items ───────────────────────────────────────────────────────────────

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Shared field names when every item is an object with the same keys and text-like values
 * (so the UI can render one textarea per field); null otherwise.
 */
export function detectItemKeys(items: Item[]): string[] | null {
  if (items.length === 0) return null;
  const first = items[0];
  if (!isRecord(first)) return null;
  const keys = Object.keys(first);
  if (keys.length === 0 || keys.length > 8) return null;
  const signature = [...keys].sort().join("\u0000");
  for (const item of items) {
    if (!isRecord(item)) return null;
    if (Object.keys(item).sort().join("\u0000") !== signature) return null;
    if (Object.values(item).some((v) => v !== null && typeof v === "object")) return null;
  }
  return keys;
}

/** Every item (including the B side of pairs) of a list of examples. */
export function itemsOf(examples: Example[]): Item[] {
  return examples.flatMap((e) => (e.item_b == null ? [e.item] : [e.item, e.item_b]));
}

/** Text value of one field for editing. */
export function fieldText(value: unknown): string {
  if (value == null) return "";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** Single-line plain text summary of an item, for search and compact rows. */
export function itemSummary(item: Item): string {
  if (typeof item === "string") return item;
  return Object.entries(item)
    .map(([k, v]) => `${k}: ${fieldText(v)}`)
    .join(" · ");
}

/** Parse raw JSON input into an item; a JSON string literal or bare text becomes a string item. */
export function parseItemJson(text: string): { item: Item } | { error: string } {
  const trimmed = text.trim();
  if (!trimmed) return { error: "Item is empty" };
  try {
    const value: unknown = JSON.parse(trimmed);
    if (typeof value === "string" || isRecord(value)) return { item: value as Item };
    return { error: "Item must be a JSON object or string" };
  } catch (e) {
    return { error: `Invalid JSON: ${e instanceof Error ? e.message : String(e)}` };
  }
}

export function isEmptyItem(item: Item): boolean {
  if (typeof item === "string") return !item.trim();
  return Object.values(item).every((v) => v == null || (typeof v === "string" && !v.trim()));
}

// ── Labels ──────────────────────────────────────────────────────────────

export type ExampleKind = "item" | "pair";

/** Labels an example of this kind may carry; mirrors spec.valid_example_labels. */
export function allowedLabels(outputType: OutputType, kind: ExampleKind, labels: OutputLabel[]): string[] {
  if (kind === "pair") return [...PAIR_LABELS];
  if (outputType === "choice") return labels.map((l) => l.id);
  return [...PREFERENCE_ITEM_LABELS];
}

export function labelText(label: string, kind: ExampleKind): string {
  if (kind === "pair") return label === "a" ? "A better" : "B better";
  return label;
}

/** Example ids the head gets wrong in the latest train + held-out evaluation. */
export function mistakeIds(metrics: Metrics | null | undefined): Set<string> {
  const ids = new Set<string>();
  if (!metrics) return ids;
  for (const row of [...metrics.train.rows, ...metrics.eval.rows]) {
    if (row.predicted !== row.label) ids.add(row.example_id);
  }
  return ids;
}

/** example_id -> predicted label from the latest evaluation. */
export function predictedById(metrics: Metrics | null | undefined): Map<string, string> {
  const map = new Map<string, string>();
  if (!metrics) return map;
  for (const row of [...metrics.train.rows, ...metrics.eval.rows]) map.set(row.example_id, row.predicted);
  return map;
}

// ── Rubric diffs ────────────────────────────────────────────────────────

function sameQuestion(a: RubricQuestion, b: RubricQuestion): boolean {
  return a.type === b.type && a.prompt === b.prompt && JSON.stringify(a.criteria) === JSON.stringify(b.criteria);
}

/**
 * Question ids whose cached judge answers a save would invalidate. A changed description
 * (or seed set) is part of every question's context, so it invalidates all of them.
 */
export function invalidatedQuestions(
  before: { description: string; rubric: RubricQuestion[] },
  after: { description: string; rubric: RubricQuestion[] },
): string[] {
  if (before.description !== after.description) return after.rubric.map((q) => q.id);
  const old = new Map(before.rubric.map((q) => [q.id, q]));
  return after.rubric.filter((q) => {
    const prev = old.get(q.id);
    return !prev || !sameQuestion(prev, q);
  }).map((q) => q.id);
}

/** First validation problem in a rubric/labels edit, or null. Mirrors backend spec.py. */
export function rubricProblem(outputType: OutputType, labels: OutputLabel[], rubric: RubricQuestion[]): string | null {
  if (outputType === "choice") {
    if (labels.length < 2 || labels.length > 12) return "Choice models need 2–12 labels";
    const ids = labels.map((l) => l.id);
    if (ids.some((id) => !isSlug(id))) return "Label ids must be lowercase slugs (a-z, 0-9, _ or -)";
    if (new Set(ids).size !== ids.length) return "Label ids must be unique";
  }
  if (rubric.length > MAX_QUESTIONS) return `At most ${MAX_QUESTIONS} questions`;
  const qids = rubric.map((q) => q.id);
  if (new Set(qids).size !== qids.length) return "Question ids must be unique";
  for (const q of rubric) {
    if (!isSlug(q.id)) return `Question id "${q.id}" must be a lowercase slug`;
    if (!q.prompt.trim()) return `Question ${q.id} needs a prompt`;
    if (q.type === "choice") {
      const keys = Array.isArray(q.criteria) ? [] : Object.keys(q.criteria);
      if (keys.length < 2 || keys.length > 12) return `${q.id}: choice questions need 2–12 options`;
      if (keys.some((k) => !k.trim())) return `${q.id}: option names must not be blank`;
    }
    if (q.type === "score" && (!Array.isArray(q.criteria) || q.criteria.length < 2 || q.criteria.length > 10)) {
      return `${q.id}: score questions need 2–10 levels`;
    }
  }
  return null;
}

/** Criteria to start from when a question changes type. */
export function defaultCriteria(type: RubricQuestion["type"]): RubricQuestion["criteria"] {
  if (type === "noul") return { true: "", false: "" };
  if (type === "choice") return { option_a: "", option_b: "" };
  return ["Low", "Medium", "High"];
}

// ── Import ──────────────────────────────────────────────────────────────

export interface ParsedImport {
  examples: NewExample[];
  errors: string[];
}

/**
 * Parse pasted JSONL: one {item, item_b?, label?, split?} per line.
 * Unlabeled lines are imported as needs_review (the backend requires that).
 */
export function parseJsonl(text: string, outputType: OutputType, labels: OutputLabel[]): ParsedImport {
  const examples: NewExample[] = [];
  const errors: string[] = [];
  text.split("\n").forEach((raw, i) => {
    const line = raw.trim();
    if (!line) return;
    const where = `Line ${i + 1}`;
    let value: unknown;
    try {
      value = JSON.parse(line);
    } catch {
      errors.push(`${where}: not valid JSON`);
      return;
    }
    if (!isRecord(value)) return void errors.push(`${where}: expected an object`);
    const { item, item_b, label, split, note } = value;
    if (!(typeof item === "string" || isRecord(item))) return void errors.push(`${where}: "item" must be a string or object`);
    if (item_b != null && !(typeof item_b === "string" || isRecord(item_b))) return void errors.push(`${where}: "item_b" must be a string or object`);
    const kind: ExampleKind = item_b != null ? "pair" : "item";
    if (kind === "pair" && outputType !== "preference") return void errors.push(`${where}: pairs only belong to preference models`);
    if (label != null && typeof label !== "string") return void errors.push(`${where}: "label" must be a string`);
    if (typeof label === "string" && !allowedLabels(outputType, kind, labels).includes(label)) {
      return void errors.push(`${where}: label must be one of ${allowedLabels(outputType, kind, labels).join(", ")}`);
    }
    if (split != null && split !== "train" && split !== "eval") return void errors.push(`${where}: split must be train or eval`);
    examples.push({
      item: item as Item,
      ...(item_b != null ? { item_b: item_b as Item } : {}),
      label: typeof label === "string" ? label : null,
      ...(split ? { split: split as Split } : {}),
      needs_review: typeof label !== "string",
      ...(typeof note === "string" ? { note } : {}),
    });
  });
  return { examples, errors };
}

// ── Formatting ──────────────────────────────────────────────────────────

export function pct(value: number | null | undefined, digits = 0): string {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 3): string {
  return value == null ? "—" : value.toFixed(digits);
}

export function signed(value: number, digits = 2): string {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(digits)}`;
}

/** Subtle diverging background for a weight: green positive, red negative. */
export function weightColor(value: number, maxAbs: number): string {
  if (!Number.isFinite(value) || maxAbs <= 0 || value === 0) return "transparent";
  const alpha = Math.min(1, Math.abs(value) / maxAbs) * 0.28;
  return value > 0 ? `rgba(34,197,94,${alpha.toFixed(3)})` : `rgba(239,68,68,${alpha.toFixed(3)})`;
}

// ── Flags & provenance ──────────────────────────────────────────────────

/** Whether a label id is marked "needs fixing" in this label set. */
export function isFlagged(labels: OutputLabel[] | undefined, id: string): boolean {
  return !!labels?.some((l) => l.id === id && l.flag);
}

/** Who produced an item field, by naming convention: agent_* (the agent's claims) vs environment_* (recorded). */
export function fieldProvenance(key: string): "agent" | "environment" | null {
  if (key.startsWith("agent_")) return "agent";
  if (key.startsWith("environment_")) return "environment";
  return null;
}

// ── Why (drivers) ───────────────────────────────────────────────────────

/** Largest |contribution|, never 0, so bars can be scaled against it. */
export function driverScale(drivers: Driver[]): number {
  return Math.max(1e-9, ...drivers.map((d) => (Number.isFinite(d.contribution) ? Math.abs(d.contribution) : 0)));
}

/** Diverging bar geometry: which side of zero and how far (0–50% of the track). */
export function driverBar(value: number, scale: number): { side: "pos" | "neg"; width: number } {
  const v = Number.isFinite(value) ? value : 0;
  const width = scale > 0 ? Math.min(1, Math.abs(v) / scale) * 50 : 0;
  return { side: v >= 0 ? "pos" : "neg", width };
}

/** Compact text for one rubric answer: "yes 72%" for yes/no, the top option otherwise. */
export function answerSummary(question: RubricQuestion | null | undefined, answer: Record<string, number> | undefined): string | null {
  if (!answer) return null;
  if (!question || question.type === "noul") {
    const p = pYes(answer);
    if (p != null) return p >= 0.5 ? `yes ${pct(p)}` : `no ${pct(1 - p)}`;
  }
  const entries = Object.entries(answer).filter(([, v]) => Number.isFinite(v));
  if (entries.length === 0) return null;
  const [key, value] = entries.reduce((best, e) => (e[1] > best[1] ? e : best));
  if (question?.type === "score" && Array.isArray(question.criteria)) {
    const text = question.criteria[Number(key)];
    return `${key}${text ? ` · ${text}` : ""} ${pct(value)}`;
  }
  return `${key} ${pct(value)}`;
}

// ── Per-question diagnostics ────────────────────────────────────────────

/**
 * How much the head leans on each question: the spread of its weights across classes
 * (|weight| for a single-score preference head), summed over the question's features.
 */
export function questionImportance(head: Head | null | undefined, rubric: RubricQuestion[]): Map<string, number> {
  const out = new Map<string, number>();
  if (!head) return out;
  head.feature_names.forEach((name, f) => {
    const { questionId } = describeFeature(name, rubric);
    const column = head.weights.map((row) => row[f] ?? 0);
    const spread = column.length === 1 ? Math.abs(column[0]) : Math.max(...column) - Math.min(...column);
    out.set(questionId, (out.get(questionId) ?? 0) + (Number.isFinite(spread) ? spread : 0));
  });
  return out;
}

export type QuestionVerdict = "helps" | "calibration" | "none" | "hurts";

/**
 * What the held-out ablation says about a question. "helps": removing it costs accuracy;
 * "calibration": accuracy unchanged but confidences get worse without it; "none": no
 * held-out benefit; "hurts": the head does better without it.
 */
export function questionVerdict(ablation: QuestionAblation | null | undefined): QuestionVerdict | null {
  if (!ablation || ablation.accuracy_drop == null) return null;
  const drop = ablation.accuracy_drop;
  const rise = ablation.log_loss_rise ?? 0;
  if (drop > 1e-9) return "helps";
  if (drop < -1e-9) return "hurts";
  return rise > 1e-3 ? "calibration" : "none";
}

/** Mean answer per label for one question, as option rows in display order. */
export function byLabelAnswers(
  question: RubricQuestion | null,
  questionId: string,
  byLabel: Record<string, Record<string, number>>,
  labelOrder: string[] = [],
): { label: string; values: { key: string; text: string; value: number }[] }[] {
  const labels = [...labelOrder.filter((l) => l in byLabel), ...Object.keys(byLabel).filter((l) => !labelOrder.includes(l))];
  return labels.map((label) => {
    const means = byLabel[label] ?? {};
    if (question?.type === "noul" || (!question && questionId in means)) {
      return { label, values: [{ key: questionId, text: "P(yes)", value: means[questionId] ?? 0 }] };
    }
    const options = question ? questionOptions(question) : Object.keys(means).map((f) => ({ key: f.slice(f.indexOf("=") + 1), label: f }));
    return {
      label,
      values: options.map((o) => ({ key: o.key, text: o.key, value: means[`${questionId}=${o.key}`] ?? 0 })),
    };
  });
}

/** The option whose mean answer differs most between labels: the one worth showing per label. */
export function separatingOption(rows: { values: { key: string; value: number }[] }[]): string | undefined {
  const keys = rows[0]?.values.map((v) => v.key) ?? [];
  let best: string | undefined;
  let bestSpread = -1;
  for (const key of keys) {
    const vals = rows.map((r) => r.values.find((v) => v.key === key)?.value ?? 0);
    const spread = Math.max(...vals) - Math.min(...vals);
    if (spread > bestSpread) [best, bestSpread] = [key, spread];
  }
  return best;
}

// ── Batch eval input ────────────────────────────────────────────────────

export const MAX_BATCH = 200;

export interface ParsedBatch {
  items: Item[];
  /** One entry per item; null where the line had no label. */
  labels: (string | null)[];
  errors: string[];
}

/**
 * Parse pasted eval data, one item per line: {"item": ..., "label"?: ...}, a JSON string,
 * a bare JSON object (the item itself), or plain text. `allowed` validates labels.
 */
export function parseBatchInput(text: string, allowed: string[] | null, max = MAX_BATCH): ParsedBatch {
  const items: Item[] = [];
  const labels: (string | null)[] = [];
  const errors: string[] = [];
  text.split("\n").forEach((raw, i) => {
    const line = raw.trim();
    if (!line) return;
    const where = `Line ${i + 1}`;
    let value: unknown = line;
    if (/^[[{"]/.test(line)) {
      try {
        value = JSON.parse(line);
      } catch {
        return void errors.push(`${where}: not valid JSON`);
      }
    }
    let item: unknown = value;
    let label: unknown = null;
    if (isRecord(value) && "item" in value) {
      item = value.item;
      label = value.label ?? null;
    }
    if (!(typeof item === "string" || isRecord(item))) return void errors.push(`${where}: item must be text or a JSON object`);
    if (isEmptyItem(item as Item)) return void errors.push(`${where}: item is empty`);
    if (label != null && typeof label !== "string") return void errors.push(`${where}: "label" must be a string`);
    if (typeof label === "string" && allowed && !allowed.includes(label)) return void errors.push(`${where}: label must be one of ${allowed.join(", ")}`);
    items.push(item as Item);
    labels.push(typeof label === "string" ? label : null);
  });
  if (items.length > max) errors.unshift(`${items.length} items; at most ${max} per run`);
  return { items, labels, errors };
}

/** Examples as eval JSONL lines ({"item", "label"}), for prefilling the eval box. */
export function examplesToJsonl(examples: Example[]): string {
  return examples
    .filter((e) => e.item_b == null)
    .map((e) => JSON.stringify(e.label ? { item: e.item, label: e.label } : { item: e.item }))
    .join("\n");
}
