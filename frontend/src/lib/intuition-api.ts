import { apiFetch } from "@/lib/api";

/** Client for /api/v1/intuitions (backend/routers/intuitions.py). */
const IM = "/api/v1/intuitions";

export type OutputType = "choice" | "preference";
export type QuestionType = "noul" | "choice" | "score";
export type ExampleSource = "human" | "agent" | "generated" | "production";
export type Split = "train" | "eval";
export type Item = string | Record<string, unknown>;

/** `flag`: this label means "needs fixing"; checks report it as a finding. */
export interface OutputLabel { id: string; description: string; flag?: boolean }
/** noul: criteria {true, false}; choice: {option: description}; score: ordered level descriptions. */
export interface RubricQuestion { id: string; type: QuestionType; prompt: string; criteria: Record<string, string> | string[] }

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
}
export interface FitOptions { l2: number; train_on: "train" | "all"; sources: ExampleSource[] | null; calibrate: boolean; rows: number }
/** Per-question diagnostics from the last fit (spec: service._question_diagnostics). */
export interface QuestionAblation { accuracy_without: number | null; log_loss_without: number | null; accuracy_drop: number | null; log_loss_rise: number | null }
export interface QuestionDiagnostic {
  question_id: string;
  /** label (or "preferred"/"not preferred" for pairs) -> feature name -> mean feature value. */
  by_label: Record<string, Record<string, number>>;
  /** Held-out effect of refitting without this question; null with too few held-out examples. */
  ablation: QuestionAblation | null;
}
export interface QuestionDiagnostics { baseline: { accuracy: number | null; log_loss: number | null } | null; questions: QuestionDiagnostic[] }
export interface Metrics {
  train: Evaluation;
  eval: Evaluation;
  ungraded_examples: number;
  fit_options: FitOptions | null;
  /** Missing on older or hand-edited heads. */
  questions?: QuestionDiagnostics | null;
}
export interface GateCheck { name: string; passed: boolean; detail: string }
export interface Gate {
  passed: boolean;
  checks: GateCheck[];
  incumbent: { n: number; accuracy: number | null; log_loss: number | null; ece: number | null } | null;
  active_version: number | null;
  forced?: boolean;
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

export interface JudgeStatus { provider: "jev"; configured: boolean; model: string }

export interface ModelSummary {
  id: string; name: string; output_type: OutputType; when_to_use?: string;
  active_version_id: string | null; draft_version_id: string | null;
  created_at: string; updated_at: string;
  active_number: number | null; active_metrics: Metrics | null;
  active_description: string | null; draft_description: string | null;
  examples: number; inbox: number;
}

export interface ModelDetail {
  model: { id: string; name: string; output_type: OutputType; when_to_use?: string; active_version_id: string | null; draft_version_id: string | null; created_at: string; updated_at: string };
  active: Version | null;
  draft: Version | null;
  versions: VersionSummary[];
  /** ungraded: items the draft needs before fitting; ungraded_total also includes the active version's. */
  counts: { total: number; labeled: number; needs_review: number; eval: number; inbox: number; ungraded: number; ungraded_total: number };
  judge: JudgeStatus;
}

export interface Example {
  id: string; model_id: string; kind: "item" | "pair";
  item: Item; item_b: Item | null; label: string | null;
  source: ExampleSource; split: Split; needs_review: boolean; note: string; created_at: string;
}
export interface NewExample { item: Item; item_b?: Item | null; label?: string | null; split?: Split; needs_review?: boolean; note?: string }

/**
 * One question's push on a decision: toward the predicted label (choice), the score
 * (preference item), or A over B (compare). Sorted by |contribution|.
 */
export interface Driver { question_id: string; prompt: string; contribution: number }

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
  drivers?: Driver[];
  version: number;
  score?: number;
}
export interface Comparison {
  prediction_id: string | null;
  score_a: number; score_b: number; p_a_wins: number; winner: "a" | "b"; confidence: number;
  contributions: Record<string, number>;
  drivers?: Driver[];
  rubric_a: RubricAnswers; rubric_b: RubricAnswers; version: number;
}
export interface LoggedPrediction {
  id: string; kind: "predict" | "compare"; input: { item: Item; item_b?: Item };
  output: (Prediction | Comparison) & Record<string, unknown>;
  confidence: number | null; caller: string; status: "unreviewed" | "labeled" | "dismissed";
  example_id: string | null; created_at: string; version: number;
}

export interface GradeResult { graded: number; failed: number; remaining: number; errors: string[] }
export interface FitResult { head: Head; metrics: Metrics; gate: Gate }

export interface CatalogExample {
  slug: string; name: string; when_to_use: string; output_type: OutputType;
  labels: { id: string; flag: boolean }[]; examples: number; attribution: string | null;
}
export interface FoundModel { model_id: string; name: string; output_type: OutputType; when_to_use: string; reason: string }
export interface CheckResult {
  model_id: string; name: string; label: string; label_meaning: string; confidence: number;
  flagged: boolean; why: Driver[]; prediction_id: string | null;
}
export interface CheckResponse {
  passed: boolean;
  findings: CheckResult[];
  results: CheckResult[];
  errors: { model_id: string; error: string }[];
  /** Models picked from `task` (null when model_ids were given). */
  routed: FoundModel[] | null;
}
export interface BatchRow {
  label: string; probabilities: Record<string, number>; confidence: number; drivers: Driver[];
  version: number; score?: number; prediction_id?: string; expected?: string; correct?: boolean;
}
export interface BatchSummary {
  n: number; label_counts: Record<string, number>; mean_confidence: number; flagged: number;
  labeled?: number; accuracy?: number; log_loss?: number; brier?: number;
}
export interface BatchResponse { version: number; summary: BatchSummary; results: BatchRow[] }

const post = <T>(path: string, body?: unknown) =>
  apiFetch<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const imList = () => apiFetch<{ models: ModelSummary[]; judge: JudgeStatus }>(IM);
export const imCreate = (body: { name: string; output_type: OutputType; when_to_use?: string; description?: string; labels?: OutputLabel[]; rubric?: RubricQuestion[] }) =>
  post<ModelDetail>(IM, body);
export const imCatalog = () => apiFetch<{ examples: CatalogExample[] }>(`${IM}/examples`);
export const imLoadExample = (slug: string) => post<ModelDetail>(`${IM}/examples/${encodeURIComponent(slug)}`);
export const imGet = (id: string) => apiFetch<ModelDetail>(`${IM}/${id}`);
export const imUpdateModel = (id: string, body: { name?: string; when_to_use?: string }) =>
  apiFetch<ModelDetail>(`${IM}/${id}`, { method: "PATCH", body: JSON.stringify(body) });
export const imRename = (id: string, name: string) => imUpdateModel(id, { name });
export const imDelete = (id: string) => apiFetch<void>(`${IM}/${id}`, { method: "DELETE" });

export const imEditDraft = (id: string, body: { description?: string; labels?: OutputLabel[]; rubric?: RubricQuestion[]; seed_example_ids?: string[] }) =>
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
export const imGenerate = (id: string, body: { count?: number; guidance?: string }) => post<Example[]>(`${IM}/${id}/examples/generate`, body);
export const imEditExample = (id: string, exampleId: string, body: { label?: string | null; split?: Split; needs_review?: boolean; note?: string }) =>
  apiFetch<Example>(`${IM}/${id}/examples/${exampleId}`, { method: "PATCH", body: JSON.stringify(body) });
export const imDeleteExample = (id: string, exampleId: string) => apiFetch<void>(`${IM}/${id}/examples/${exampleId}`, { method: "DELETE" });

export const imPredict = (id: string, item: Item, version: "active" | "draft" = "active") =>
  post<Prediction>(`${IM}/${id}/predict`, { item, version, caller: "playground" });
export const imCompare = (id: string, item_a: Item, item_b: Item, version: "active" | "draft" = "active") =>
  post<Comparison>(`${IM}/${id}/compare`, { item_a, item_b, version, caller: "playground" });
export const imPredictions = (id: string, status: "unreviewed" | "labeled" | "dismissed" | "all" = "unreviewed") =>
  apiFetch<LoggedPrediction[]>(`${IM}/${id}/predictions?status=${status}`);
export const imReview = (id: string, predictionId: string, body: { label?: string | null; dismiss?: boolean; note?: string }) =>
  post<{ status: string; example: Example | null }>(`${IM}/${id}/predictions/${predictionId}/review`, body);

export const imFind = (task: string, limit = 5) => apiFetch<{ models: FoundModel[] }>(`${IM}/find?${new URLSearchParams({ task, limit: String(limit) })}`);
export const imCheck = (body: { item: Item; model_ids?: string[]; task?: string; caller?: string }) => post<CheckResponse>(`${IM}/check`, { caller: "playground", ...body });
export const imBatch = (id: string, body: { items: Item[]; labels?: (string | null)[]; version?: "active" | "draft"; log?: boolean }) =>
  post<BatchResponse>(`${IM}/${id}/batch`, { caller: "eval", ...body });
