import { apiFetch } from "@/lib/api";

const WB = "/api/v1/rm/workbench";
export type Verdict = "meets" | "violates" | "insufficient_evidence" | "not_applicable";
export type ChangeKind = "judge_error" | "agent_error" | "both" | "requirement_change" | "label_only" | "unclear";
export interface GraderCriterion { id: string; name: string; description: string }
export interface WorkbenchScope { repository?: string; source_format?: string }
export interface GraderConfig { prompt: string; criteria: GraderCriterion[]; examples: { criterion_id: string; input: string; verdict: Verdict; note?: string }[]; model: string; provider?: "jev"; max_context_chars?: number }
export interface GraderVersion { id: string; grader_id: string; version: number; config: GraderConfig; created_at: string }
export interface Grader {
  id: string; name: string; scope: WorkbenchScope; active_version_id: string | null;
  enabled: boolean; active_version?: GraderVersion; created_at: string;
}
export interface GraderDetail { grader: Grader; versions: GraderVersion[]; history?: unknown[] }
export interface AssessmentResponse { assessments: Assessment[]; coverage: { total_actions: number; assessed_actions: number; pending: number; failed: number; queue_status?: string | null; last_error?: string | null }; graders: Grader[]; owner_user_id?: string; feedback?: WorkbenchFeedback[] }
export interface Assessment {
  id: string; trace_id: string; target_step_id: string | null;
  criterion_id: string; criterion_name: string; grader_version_id: string; grader_id: string; target_index: number;
  status: "queued" | "running" | "completed" | "failed";
  verdict: Verdict | null; reason: string | null; input_snapshot: unknown;
  raw_output: unknown; evidence_step_ids: string[]; error: string | null;
  created_at: string; usage?: unknown; mode?: string;
}
export interface WorkbenchFeedback {
  id: string; trace_id: string; assessment_id: string | null; target_step_id: string | null; source_event_id?: string | null;
  comment: string; proposed_verdict: Verdict | null; change_kind: ChangeKind;
  interpretation: unknown; review_status: string; source?: string; status: string; error?: string | null;
  author_user_id: string; created_at: string; updated_at?: string; changes?: WorkbenchChange[];
  history?: unknown[];
}
export interface WorkbenchChange {
  id: string; kind: "grader" | "instruction"; status: string; title: string;
  feedback_id: string | null; content: { config?: GraderConfig; text?: string };
  parent_version_id?: string | null; grader_id: string | null;
  check_report: Record<string, unknown> | null;
  error?: string | null;
  scope?: WorkbenchScope; previous_content?: WorkbenchChange["content"] | null;
  created_at: string; released_at: string | null;
  delivery_records?: InstructionDelivery[];
  skill_id?: string | null;
  history?: unknown[];
}
export interface InstructionDelivery { id: string; grader_id: string; release_id: string; change_id: string; session_id: string; source_format: string; repository: string; content: string; content_sha256: string; status: "offered" | "captured"; trace_id: string | null; step_id: string | null; offered_at: string; captured_at: string | null }
export const verdictOptions: { value: Verdict; label: string }[] = [
  { value: "meets", label: "Meets criterion" }, { value: "violates", label: "Violates criterion" },
  { value: "insufficient_evidence", label: "Insufficient evidence" }, { value: "not_applicable", label: "Not applicable" },
];

export function wbStatus(): Promise<{ provider: string; configured: boolean; model: string }> { return apiFetch(`${WB}/status`); }
export function wbListGraders(): Promise<Grader[]> { return apiFetch(`${WB}/graders`); }
export function wbGetGrader(id: string): Promise<GraderDetail> { return apiFetch(`${WB}/graders/${id}`); }
export function wbCreateGrader(body: { name: string; scope: WorkbenchScope; config: GraderConfig }): Promise<Grader> { return apiFetch(`${WB}/graders`, { method: "POST", body: JSON.stringify(body) }); }
export function wbCreateVersion(id: string, config: GraderConfig): Promise<WorkbenchChange> { return apiFetch(`${WB}/graders/${id}/versions`, { method: "POST", body: JSON.stringify({ config }) }); }
export function wbUpdateGrader(id: string, body: { enabled: boolean }): Promise<Grader> { return apiFetch(`${WB}/graders/${id}`, { method: "PATCH", body: JSON.stringify(body) }); }
export function wbAssessments(traceId: string): Promise<AssessmentResponse> { return apiFetch(`${WB}/traces/${traceId}/assessments`); }
export function wbAssess(traceId: string): Promise<unknown> { return apiFetch(`${WB}/traces/${traceId}/assess`, { method: "POST" }); }
export function wbListFeedback(): Promise<WorkbenchFeedback[]> { return apiFetch(`${WB}/feedback`); }
export function wbFeedbackDetail(id: string): Promise<WorkbenchFeedback> { return apiFetch(`${WB}/feedback/${id}`); }
export function wbCreateFeedback(body: { trace_id: string; assessment_id?: string; evaluation_id?: string; target_step_id?: string; comment: string; proposed_verdict?: Verdict; change_kind: ChangeKind }): Promise<WorkbenchFeedback> { return apiFetch(`${WB}/feedback`, { method: "POST", body: JSON.stringify(body) }); }
export function wbReviewFeedback(id: string, body: { decision: "accept" | "reject"; proposed_verdict?: Verdict; change_kind?: ChangeKind }): Promise<WorkbenchFeedback> { return apiFetch(`${WB}/feedback/${id}/review`, { method: "POST", body: JSON.stringify(body) }); }
export function wbRetryFeedback(id: string): Promise<WorkbenchFeedback> { return apiFetch(`${WB}/feedback/${id}/retry`, { method: "POST" }); }
export interface ReviewSample { assessment: Assessment; reason: "violation" | "uncertain" | "sample" }
export function wbReviewSamples(): Promise<ReviewSample[]> { return apiFetch(`${WB}/review-samples`); }
export function wbLabelAssessment(id: string, verdict: Verdict, comment?: string): Promise<WorkbenchFeedback> { return apiFetch(`${WB}/assessments/${id}/label`, { method: "POST", body: JSON.stringify({ verdict, ...(comment ? { comment } : {}) }) }); }
export function wbListChanges(): Promise<WorkbenchChange[]> { return apiFetch(`${WB}/changes`); }
export function wbGetChange(id: string): Promise<WorkbenchChange> { return apiFetch(`${WB}/changes/${id}`); }
export function wbEditChange(id: string, content: WorkbenchChange["content"]): Promise<WorkbenchChange> { return apiFetch(`${WB}/changes/${id}`, { method: "PATCH", body: JSON.stringify({ content }) }); }
export function wbCheckChange(id: string): Promise<WorkbenchChange> { return apiFetch(`${WB}/changes/${id}/check`, { method: "POST" }); }
export function wbReleaseChange(id: string, acceptUnmeasured = false): Promise<WorkbenchChange> { return apiFetch(`${WB}/changes/${id}/release`, { method: "POST", body: JSON.stringify({ accept_unmeasured: acceptUnmeasured }) }); }
export function wbRejectChange(id: string): Promise<WorkbenchChange> { return apiFetch(`${WB}/changes/${id}/reject`, { method: "POST" }); }
export interface InstructionRelease { id: string; change_id: string | null; previous_change_id: string | null; action: "release" | "rollback" | "disable"; scope: WorkbenchScope; content: string | null; created_at: string; active: boolean }
export function wbInstructionReleases(graderId: string): Promise<InstructionRelease[]> { return apiFetch(`${WB}/graders/${graderId}/instruction-releases`); }
export function wbRollbackInstruction(graderId: string, changeId: string | null): Promise<unknown> { return apiFetch(`${WB}/graders/${graderId}/instruction-rollback`, { method: "POST", body: JSON.stringify({ change_id: changeId }) }); }
export function wbRollbackGrader(graderId: string, versionId: string): Promise<GraderDetail> { return apiFetch(`${WB}/graders/${graderId}/rollback`, { method: "POST", body: JSON.stringify({ version_id: versionId }) }); }
export interface TraceReviewers { owner_user_id: string; reviewers: { user_id: string; display_name: string; email: string }[] }
export function wbTraceReviewers(traceId: string): Promise<TraceReviewers> { return apiFetch(`${WB}/traces/${traceId}/reviewers`); }
export function wbReviewerSuggestions(traceId: string, query: string): Promise<TraceReviewers["reviewers"]> { return apiFetch(`${WB}/traces/${traceId}/reviewer-suggestions?q=${encodeURIComponent(query)}`); }
export function wbAddReviewer(traceId: string, email: string): Promise<TraceReviewers> { return apiFetch(`${WB}/traces/${traceId}/reviewers`, { method: "POST", body: JSON.stringify({ email }) }); }
export function wbRemoveReviewer(traceId: string, userId: string): Promise<TraceReviewers> { return apiFetch(`${WB}/traces/${traceId}/reviewers/${userId}`, { method: "DELETE" }); }

export interface EvaluationCall {
  id: string; batch_index: number; attempt: number; status: string; error: string | null;
  input_snapshot: { context_events?: { id: string; index: number; role: string; content: string }[]; omissions?: unknown[]; [key: string]: unknown };
  raw_output: unknown; result: unknown;
}
export interface TraceEvaluation {
  id: string; trace_id: string; revision_hash: string; policy_version: string; status: string;
  outcome: string | null; outcome_probabilities?: Record<string, number> | null; outcome_confidence: number | null; total_actions: number; credited_actions: number;
  error: string | null; created_at: string; boundary: { kind: string; step_index: number };
  // `credit` retains the legacy ordinal (-2..2); expected_credit is continuous (-1..1).
  credits: { step_id: string; index: number; credit: number | null; expected_credit?: number | null; credit_method?: string; label: string; confidence: number; call_id: string }[];
  actions: { id: string; index: number; content: string; tool_name: string | null }[];
  calls: EvaluationCall[];
}
export interface TraceEvaluationResponse {
  provider: string; model: string; configured: boolean; policy_version: string; owner_user_id: string;
  boundary: TraceEvaluation["boundary"] | null; queue: { status: string; error: string | null } | null;
  current: TraceEvaluation | null; history: Pick<TraceEvaluation, "id" | "outcome" | "status" | "created_at" | "boundary">[];
  previous_credits?: (TraceEvaluation["credits"][number] & { evaluation_id: string; created_at: string })[];
}
export function wbEvaluation(traceId: string): Promise<TraceEvaluationResponse> { return apiFetch(`${WB}/traces/${traceId}/evaluation`); }
export function wbHistoricalEvaluation(traceId: string, evaluationId: string): Promise<TraceEvaluation> { return apiFetch(`${WB}/traces/${traceId}/evaluation/${evaluationId}`); }
