import { apiFetch } from "@/lib/api";

/** Client for /api/v1/intuitions (backend/routers/intuitions.py). */
const IM = "/api/v1/intuitions";

export type OutputType = "choice" | "preference" | "multi";
/** Must match spec.BRIEF_MARKER on the server; the suffix is generated from the eval brief. */
export const BRIEF_MARKER = "\n\n— From the eval brief —\n";
export type QuestionType = "noul" | "choice" | "score" | "eval" | "probe";
export type ExampleSource = "human" | "agent" | "generated" | "production";
export type Split = "train" | "eval";
export type Item = string | Record<string, unknown>;

export interface OutputLabel { id: string; description: string }
/** noul: criteria {true, false}; choice: {option: description}; score: ordered level descriptions. */
/** eval: another eval's decision used as a signal; the server fills criteria and pins version_id. */
export interface RubricQuestion { id: string; type: QuestionType; prompt: string; criteria: Record<string, string> | string[]; eval_id?: string; version_id?: string }

export interface Head {
  feature_names: string[];
  classes: string[];
  weights: number[][];
  bias: number[];
  temperature: number;
  l2: number | null;
  edited: boolean;
  fit: { converged: boolean; iterations: number; train_rows: number } | null;
}

export interface EvalRow { example_id: string; label: string; predicted: string; p_true: number }
export interface Evaluation {
  n: number;
  accuracy: number | null;
  log_loss: number | null;
  ece: number | null;
  reliability?: { bin: number; n: number; confidence: number; accuracy: number }[];
  confusion: Record<string, Record<string, number>> | null;
  rows: EvalRow[];
  classification?: Classification | null;
  /** Accuracy by input size (characters), bucketed 1..10 from easiest to hardest. */
  by_difficulty?: DifficultyBucket[];
}
export interface DifficultyBucket { bucket: number; n: number; difficulty: [number, number]; accuracy: number | null }
export interface ClassMetrics { precision: number | null; recall: number | null; f1: number | null; support: number }
export interface Classification { per_class: Record<string, ClassMetrics>; macro_f1: number | null; kappa: number | null }
export interface FitOptions { l2: number; train_on: "train" | "all"; sources: ExampleSource[] | null; calibrate: boolean; rows: number }
export interface Metrics { train: Evaluation; eval: Evaluation; ungraded_examples: number; fit_options: FitOptions | null }
/** Blocking checks are regressions; advisory ones (e.g. a small held-out set) never stop a save. */
export interface GateCheck { name: string; passed: boolean; detail: string; blocking?: boolean }
export interface Flip { example_id: string; label: string; active: string; candidate: string; pinned: boolean }
export interface Gate {
  passed: boolean;
  checks: GateCheck[];
  incumbent: { n: number; accuracy: number | null; log_loss: number | null; ece: number | null } | null;
  active_version: number | null;
  forced?: boolean;
  flips?: Flip[];
  /** Held-out or pinned examples the live version got wrong and this one gets right. */
  fixes?: Flip[];
  pinned?: { n: number; accuracy: number | null; rows: EvalRow[] };
}

export interface Version {
  id: string;
  model_id: string;
  number: number;
  status: "draft" | "active" | "retired";
  output_type: OutputType;
  description: string;
  labels: OutputLabel[];
  rubric: RubricQuestion[];
  seed_example_ids: string[];
  provider: string;
  provider_model: string;
  head: Head | null;
  metrics: Metrics | null;
  gate: Gate | null;
  parent_version_id: string | null;
  promoted_at: string | null;
  created_at: string;
  feature_names: string[];
  classes: string[];
  head_stale: boolean;
}

export interface VersionSummary {
  id: string; number: number; status: Version["status"]; provider: string; provider_model: string;
  metrics: Metrics | null; gate: Gate | null; promoted_at: string | null; created_at: string;
  parent_version_id: string | null; has_head: boolean;
}

export type JudgeProvider = "jev" | "agent_judge";
export interface JudgeStatus {
  provider: "jev"; configured: boolean; model: string;
  providers?: Record<JudgeProvider, { configured: boolean; model: string }>;
}

export interface ModelSummary {
  id: string; name: string; output_type: OutputType;
  active_version_id: string | null; draft_version_id: string | null;
  created_at: string; updated_at: string;
  active_number: number | null; active_metrics: Metrics | null;
  active_description: string | null; draft_description: string | null;
  examples: number; inbox: number;
}

export interface ModelDetail {
  model: { id: string; name: string; output_type: OutputType; active_version_id: string | null; draft_version_id: string | null; created_at: string; updated_at: string; brief?: Record<string, unknown> };
  active: Version | null;
  draft: Version | null;
  versions: VersionSummary[];
  /** ungraded: items the draft needs before fitting; ungraded_total also includes the active version's. */
  counts: { total: number; labeled: number; needs_review: number; eval: number; inbox: number; escalated?: number; pinned?: number; calibration?: number; ungraded: number; ungraded_total: number };
  judge: JudgeStatus;
}

export interface Example {
  id: string; model_id: string; kind: "item" | "pair";
  item: Item; item_b: Item | null; label: string | null;
  source: ExampleSource; split: Split; needs_review: boolean; note: string; created_at: string;
  pinned?: boolean;
  calibration?: boolean;
}
export interface NewExample { item: Item; item_b?: Item | null; label?: string | null; split?: Split; needs_review?: boolean; note?: string; pinned?: boolean }

/** Rubric answers keyed by question id, then option -> probability. */
export type RubricAnswers = Record<string, Record<string, number>>;

export interface Prediction {
  prediction_id: string | null;
  label: string;
  probabilities: Record<string, number>;
  confidence: number;
  /** Per output class, each feature's contribution to that class's logit (preference: key "score"). */
  contributions: Record<string, Record<string, number>>;
  rubric: RubricAnswers;
  version: number;
  score?: number;
}
export interface Comparison {
  prediction_id: string | null;
  score_a: number; score_b: number; p_a_wins: number; winner: "a" | "b"; confidence: number;
  contributions: Record<string, number>;
  rubric_a: RubricAnswers; rubric_b: RubricAnswers; version: number;
}
export interface LoggedPrediction {
  id: string; kind: "predict" | "compare"; input: { item: Item; item_b?: Item };
  output: (Prediction | Comparison) & Record<string, unknown>;
  confidence: number | null; caller: string; status: "unreviewed" | "escalated" | "labeled" | "dismissed";
  example_id: string | null; created_at: string; version: number;
  ref?: string | null; metadata?: Record<string, unknown>; feedback?: FeedbackRow[];
}

export type FeedbackSource = "human" | "outcome" | "downstream";
export interface FeedbackRow { id: string; prediction_id: string; label: string | null; value: number | null; source: FeedbackSource; note: string; created_at: string }
export interface FeedbackBody { prediction_id?: string; ref?: string; label?: string; value?: number; source?: FeedbackSource; note?: string; learn?: boolean }

export interface MonitoringSummary {
  calls: number; errors: number; with_feedback: number;
  accuracy: number | null; ece: number | null; mean_confidence: number | null; mean_value: number | null;
}
export interface Monitoring {
  days: number;
  truncated: boolean;
  /** The rubric may be going stale (drift or production disagreement); refine it. */
  refine_suggested?: boolean;
  refine_reason?: string | null;
  summary: MonitoringSummary & { reliability: { bin: number; n: number; confidence: number; accuracy: number }[] };
  daily: (MonitoringSummary & { date: string; labels: Record<string, number> })[];
  versions: (MonitoringSummary & { version: number })[];
  drift: {
    window_days: number; version?: number; recent_calls: number; train_examples?: number;
    labels: { label: string; train_share: number; recent_share: number }[];
    features: { feature: string; train_mean: number; recent_mean: number; shift: number }[];
  } | null;
  disagreements: {
    prediction_id: string; created_at: string; ref: string | null; version: number;
    predicted: string; truth: string; truth_source: FeedbackSource; confidence: number; preview: string;
    top_feature: { feature: string; contribution: number } | null;
  }[];
}

export interface GradeResult { graded: number; failed: number; remaining: number; errors: string[] }
export interface FitResult { head: Head; metrics: Metrics; gate: Gate }

const post = <T>(path: string, body?: unknown) =>
  apiFetch<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const imList = () => apiFetch<{ models: ModelSummary[]; judge: JudgeStatus }>(IM);
export const imCreate = (body: { name: string; output_type: OutputType; description?: string; labels?: OutputLabel[]; rubric?: RubricQuestion[] }) =>
  post<ModelDetail>(IM, body);
export const imLoadExample = () => post<ModelDetail>(`${IM}/examples/support-replies`);
export const imGet = (id: string) => apiFetch<ModelDetail>(`${IM}/${id}`);
export const imRename = (id: string, name: string) => apiFetch<ModelDetail>(`${IM}/${id}`, { method: "PATCH", body: JSON.stringify({ name }) });
export const imDelete = (id: string) => apiFetch<void>(`${IM}/${id}`, { method: "DELETE" });

export const imEditDraft = (id: string, body: { description?: string; labels?: OutputLabel[]; rubric?: RubricQuestion[]; seed_example_ids?: string[]; provider?: JudgeProvider }) =>
  apiFetch<ModelDetail>(`${IM}/${id}/draft`, { method: "PATCH", body: JSON.stringify(body) });
export const imDiscardDraft = (id: string) => apiFetch<ModelDetail>(`${IM}/${id}/draft`, { method: "DELETE" });
export const imGrade = (id: string, limit = 12) => post<GradeResult>(`${IM}/${id}/draft/grade`, { limit });
export const imFit = (id: string, body: { l2?: number; train_on?: "train" | "all"; sources?: ExampleSource[] | null; calibrate?: boolean }) =>
  post<FitResult>(`${IM}/${id}/draft/fit`, body);
export const imSetHead = (id: string, body: { weights: number[][]; bias: number[]; temperature: number }) =>
  apiFetch<FitResult>(`${IM}/${id}/draft/head`, { method: "PUT", body: JSON.stringify(body) });
export const imPromote = (id: string, force = false) => post<ModelDetail>(`${IM}/${id}/draft/promote`, { force });
export const imDraftRubric = (id: string, body: { count?: number; guidance?: string }) =>
  post<{ rationale: string; rubric: RubricQuestion[]; examples_considered: number }>(`${IM}/${id}/draft/draft-rubric`, body);
export const imSuggestQuestion = (id: string) =>
  post<{ rationale: string; question: RubricQuestion; mistakes_considered: number }>(`${IM}/${id}/draft/suggest-question`);
export const imVersion = (id: string, versionId: string) => apiFetch<Version>(`${IM}/${id}/versions/${versionId}`);
export const imRestore = (id: string, versionId: string) => post<ModelDetail>(`${IM}/${id}/versions/${versionId}/restore`);

export const imExamples = (id: string) => apiFetch<Example[]>(`${IM}/${id}/examples`);
export const imAddExamples = (id: string, examples: NewExample[], source: ExampleSource = "human") =>
  post<Example[]>(`${IM}/${id}/examples`, { examples, source });
export const imGenerate = (id: string, body: { count?: number; guidance?: string; propose?: boolean }) => post<Example[]>(`${IM}/${id}/examples/generate`, body);
export const imAcceptSuggestions = (id: string) => post<{ accepted: number }>(`${IM}/${id}/examples/accept-suggestions`);
export const imEditExample = (id: string, exampleId: string, body: { label?: string | null; split?: Split; needs_review?: boolean; note?: string; pinned?: boolean; calibration?: boolean }) =>
  apiFetch<Example>(`${IM}/${id}/examples/${exampleId}`, { method: "PATCH", body: JSON.stringify(body) });
export const imDeleteExample = (id: string, exampleId: string) => apiFetch<void>(`${IM}/${id}/examples/${exampleId}`, { method: "DELETE" });

export const imPredict = (id: string, item: Item, version: "active" | "draft" = "active") =>
  post<Prediction>(`${IM}/${id}/predict`, { item, version, caller: "playground" });
export const imCompare = (id: string, item_a: Item, item_b: Item, version: "active" | "draft" = "active") =>
  post<Comparison>(`${IM}/${id}/compare`, { item_a, item_b, version, caller: "playground" });
export const imPredictions = (id: string, status: "unreviewed" | "labeled" | "dismissed" | "all" = "unreviewed", offset = 0) =>
  apiFetch<LoggedPrediction[]>(`${IM}/${id}/predictions?status=${status}&limit=50&offset=${offset}`);
export const imFeedback = (id: string, body: FeedbackBody) =>
  post<{ feedback: FeedbackRow; prediction_id: string; example: Example | null }>(`${IM}/${id}/feedback`, body);
export const imMonitoring = (id: string, days = 30) => apiFetch<Monitoring>(`${IM}/${id}/monitoring?days=${days}`);
export const imReview = (id: string, predictionId: string, body: { label?: string | null; dismiss?: boolean; note?: string }) =>
  post<{ status: string; example: Example | null }>(`${IM}/${id}/predictions/${predictionId}/review`, body);

export const evalAddExamples = (id: string, examples: NewExample[]) => post<Example[]>(`${IM}/${id}/builder/examples`, { examples });
export const evalAddTrace = (id: string, trace_id: string, label: string, note = "") => post<Example[]>(`${IM}/${id}/builder/trace`, { trace_id, label, note });
export const evalPrepare = (id: string) => post<ModelDetail>(`${IM}/${id}/builder/prepare`);
export function evalReadFile(file: File): Promise<Item> {
  const body = new FormData(); body.set("file", file);
  return apiFetch<Item>(`${IM}/inputs`, { method: "POST", body });
}

export interface QueueItem {
  prediction_id: string; kind: "predict" | "compare"; input: { item: Item; item_b?: Item };
  predicted: string; confidence: number | null; ref: string | null; caller: string; version: number; created_at: string;
  uncertainty: number; novelty: number | null; conflict: boolean; score: number; reasons: string[];
}
export const imLabelQueue = (id: string) => apiFetch<QueueItem[]>(`${IM}/${id}/label-queue`);

export interface ImproveCandidate {
  name: "current" | "add_question" | "rewrite_weakest" | "prune" | "fresh"; title: string; rationale: string;
  questions: number; new_questions: string[]; rubric: RubricQuestion[];
  cv_log_loss: number | null; cv_accuracy: number | null; rows: number;
}
export interface ImproveJob {
  id: string; model_id: string; status: "queued" | "running" | "succeeded" | "failed";
  progress: { stage?: string; message?: string; completed?: number; total?: number };
  result: { base_version: number; winner: string; changed: boolean; candidates: ImproveCandidate[]; gate: Gate; held_out: { n: number; accuracy: number | null; log_loss: number | null } } | null;
  error: string | null; created_at: string; finished_at: string | null;
}
export const imStartImprove = (id: string) => post<ImproveJob>(`${IM}/${id}/improve`);
export const imImproveStatus = (id: string) => apiFetch<{ job: ImproveJob | null }>(`${IM}/${id}/improve`);

export interface RefineEdit { kind: string; question_id: string; rationale: string }
export interface RefinePoint { pass: number; cv_accuracy: number | null; cv_log_loss: number | null; macro_f1: number | null; questions: number; edits: RefineEdit[]; accepted: boolean; note?: string }
export interface RefineResult {
  base_version: number; changed: boolean; passes: number; curve: RefinePoint[]; rubric: RubricQuestion[];
  signals: { examples: number; production_disagreements: number; contradicted_claims: number };
  gate: Gate | null; held_out: { n: number; accuracy: number | null; log_loss: number | null } | null;
}
export interface RefineJob {
  id: string; model_id: string; kind: "refine"; status: "queued" | "running" | "succeeded" | "failed";
  progress: { stage?: string; message?: string; curve?: RefinePoint[] }; result: RefineResult | null; error: string | null;
}
export const imStartRefine = (id: string) => post<RefineJob>(`${IM}/${id}/refine`);
export const imRefineStatus = (id: string) => apiFetch<{ job: RefineJob | null }>(`${IM}/${id}/refine`);

export type CohortDimension = "agent" | "outcome" | "satisfaction" | "behavior" | "tool_use" | "task_type";
export interface MinedCriteria {
  cohort: { by: CohortDimension; key: string; traces: number }; votes: number;
  examples: { reaction: string; agent_said: string; user_replied: string }[];
  rationale: string; questions: RubricQuestion[];
}
export const imMineProduction = (id: string, body: { by: CohortDimension; key: string; days: number }) => post<MinedCriteria>(`${IM}/${id}/mine-production`, body);

export interface Credit {
  decisions: string[]; runs: number; calls: number; success_rate: number | null; minimum_runs: number;
  by_decision: { decision: string; runs: number; success_rate: number | null }[];
  ready: boolean; reason?: string;
  weights?: { decision: string; weight: number; low: number | null; high: number | null }[];
  cv_accuracy?: number | null;
  calls_by_credit?: { prediction_id: string; run: string; outcome: number; decision: string; credit: number; suspect: boolean }[];
}
export const imCredit = (id: string) => apiFetch<Credit>(`${IM}/${id}/credit`);

export interface EvalAlert { min_agreement: number; min_feedback?: number; window_days?: number; cooldown_hours?: number; channels: ("slack" | "email")[] }
/** Alert when agreement with production feedback drops; null turns it off. */
export const imSetAlert = (id: string, alert: EvalAlert | null) =>
  apiFetch<{ alert: EvalAlert | null }>(`${IM}/${id}/alert`, { method: "PUT", body: JSON.stringify(alert) });
