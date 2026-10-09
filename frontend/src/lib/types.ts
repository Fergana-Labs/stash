export type ProductCheckpoint = "latest" | "floodgate-2026-10-05";

export interface User {
  product_checkpoint?: ProductCheckpoint;
  id: string;
  developer_platform_only: boolean;
  reward_models_enabled: boolean;
  name: string;
  display_name: string;
  email?: string | null;
  description: string;
  created_at: string;
  last_seen: string;
}

export interface RegisterResponse {
  id: string;
  name: string;
  display_name: string;
  api_key: string;
}

// --- Files: folders (nested) and pages ---

export type PageContentType = "markdown" | "html";

export interface Folder {
  id: string;
  owner_user_id: string;
  parent_folder_id: string | null;
  name: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  /** Memory and Clips: code resolves these by identity and writes into them,
   *  so the service refuses to rename, move, or delete one. Clients hide those
   *  actions rather than offer what will be refused. */
  is_protected?: boolean;
}

export type HtmlLayout = "responsive" | "fixed-aspect" | "full-width";

export interface Page {
  id: string;
  owner_user_id: string;
  folder_id: string | null;
  name: string;
  content_type: PageContentType;
  content_markdown: string;
  content_html: string;
  html_layout: HtmlLayout;
  content_hash: string | null;
  /** Whether the requesting viewer may write this page. */
  can_write: boolean;
  last_edit_session_id?: string | null;
  last_edit_agent_name?: string | null;
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  rank?: number;
  similarity?: number;
}

// Lightweight tree node — pages live as `pages: PageSummary[]` in each folder.
export interface PageSummary {
  id: string;
  owner_user_id: string;
  folder_id: string | null;
  name: string;
  content_type: PageContentType;
  created_at: string;
  updated_at: string;
}

export interface FolderTreeNode extends Folder {
  folders: FolderTreeNode[];
  pages: PageSummary[];
}

export interface Tree {
  folders: FolderTreeNode[];
  pages: PageSummary[];
}

// --- Tables ---

export interface TableColumn {
  id: string;
  name: string;
  type:
    | "text"
    | "number"
    | "boolean"
    | "date"
    | "datetime"
    | "url"
    | "email"
    | "select"
    | "multiselect"
    | "json";
  order: number;
  required: boolean;
  default: string | number | boolean | string[] | null;
  options: string[] | null;
  width: number;
}

/** How a saved view renders. Views are persisted as an untyped JSONB dict, so
 *  `layout` costs nothing server-side — older views without it read as a grid. */
export type TableViewLayout = "table" | "cards";

export interface TableView {
  id: string;
  name: string;
  layout?: TableViewLayout;
  filters?: { column_id: string; op: string; value: string }[];
  sort_by?: string;
  sort_order?: string;
  visible_columns?: string[];
}

/** Which column fills each slot of a card / detail pane, by column id. The
 *  server resolves these from the manifest's column *names*, so the client
 *  never needs to know that a bookmark has a "Site". */
export interface MiniProgramDetail {
  title?: string;
  subtitle?: string;
  body?: string;
  labels?: string;
  link?: string;
  content?: string;
  badge?: string;
  timestamp?: string;
}

export interface MiniProgramManifest {
  slug: string;
  title: string;
  tagline: string;
  icon: string;
  empty_state: {
    title: string;
    description: string;
    action: { label: string; href: string };
  };
  detail: MiniProgramDetail;
  /** Columns an LLM fills in the background — rendered as pending until they do. */
  enriched_columns: string[];
}

export interface MiniProgramApp {
  slug: string;
  title: string;
  tagline: string;
  icon: string;
  installed: boolean;
  table_id: string | null;
  row_count: number;
}

/** A skill the launcher can run: the name to invoke plus the frontmatter that
 *  says what it does. Only skills in your own Skills are launchable — an agent
 *  reads its scope, not the public catalog — so this is always built from a
 *  Skill you hold. */
export interface LaunchableSkill {
  name: string;
  description: string;
  when_to_use: string;
}

/** A published skill an app's table is built for. Carries a slug because you
 *  may not hold it yet: the strip that lists these offers Add for those, and
 *  Run only once the skill is actually in your Skills. */
export interface CuratedSkill {
  name: string;
  slug: string;
  description: string;
}

export interface MiniProgramResolved {
  table_id: string;
  row_count: number;
  manifest: MiniProgramManifest;
}

export interface Table {
  id: string;
  owner_user_id: string | null;
  folder_id: string | null;
  name: string;
  description: string;
  columns: TableColumn[];
  views: TableView[];
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  row_count: number | null;
}

export interface TableRow {
  id: string;
  table_id: string;
  data: Record<string, unknown>;
  row_order: number;
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface TableWithOwner extends Table {
  owner_display_name: string | null;
}

// --- Files ---

export interface FileInfo {
  id: string;
  owner_user_id: string | null;
  folder_id?: string | null;
  // Set when the file is embedded in a page (derived from the page body's
  // download link on save; read-only). Embedded files render inside their
  // page, never as tree/grid entries.
  owner_page_id?: string | null;
  name: string;
  content_type: string;
  size_bytes: number;
  url: string;
  app_url: string;
  uploaded_by: string;
  uploaded_by_name?: string;
  uploaded_by_display_name?: string | null;
  created_at: string;
  linked_table_id?: string | null;
}

export interface Attachment {
  file_id: string;
  name: string;
  content_type: string;
}

// --- Dashboard Visualizations ---

export interface ActivityTimeline {
  contributors: string[];
  buckets: {
    date: string;
    contributors: Record<
      string,
      { total: number; by_type: Record<string, number> }
    >;
  }[];
}

export interface KnowledgeDensity {
  clusters: {
    label: string;
    count: number;
    newest_at: string | null;
  }[];
}

export interface EmbeddingProjectionPoint {
  id: string;
  x: number;
  y: number;
  z: number;
  source: "pages" | "table_rows" | "history_events";
  label: string;
  created_at: string | null;
}

export interface EmbeddingProjection {
  points: EmbeddingProjectionPoint[];
  stats: { total_embeddings: number; projected: number };
  cached: boolean;
}

// --- Page comments ---

export interface CommentMessage {
  id: string;
  thread_id: string;
  author_id: string;
  author_name: string;
  body: string;
  created_at: string;
}

export interface CommentThread {
  id: string;
  page_id: string;
  quoted_text: string;
  prefix: string;
  suffix: string;
  created_by: string;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  orphaned: boolean;
  messages: CommentMessage[];
}

// --- Search ---

export interface UserSearchResult {
  id: string;
  name: string;
  display_name: string;
}

// --- Trash ---

export type TrashKind = "page" | "file" | "session";

export interface TrashEntry {
  id: string;
  name: string;
  deleted_at: string;
  deleted_by: string | null;
  deleted_by_name: string | null;
}

export interface TrashListing {
  pages: TrashEntry[];
  files: TrashEntry[];
  sessions: TrashEntry[];
}

// --- Workspaces ---

// A workspace the signed-in user belongs to. `scope_user_id` is the synthetic
// user that owns the workspace's shared content; requests carrying it as
// X-Stash-Scope read and write the workspace knowledge base instead of the personal one.
export interface Workspace {
  id: string;
  name: string;
  /** NULL for invite-only (developer) workspaces — membership is explicit. */
  domain: string | null;
  scope_user_id: string;
  /** Set when the developer platform is active on this workspace. */
  external_wiki_folder_id: string | null;
}

/** External Multiplayer: one customer of a developer workspace. */
// One end user of a developer's product — "user" on the wire and in the
// console; EndUser here because User is a Stash account.
export interface EndUser {
  id: string;
  workspace_id: string;
  external_id: string;
  name: string;
  share_wiki: boolean;
  wiki_folder_id: string;
  created_at: string;
  session_count: number;
  last_session_at: string | null;
}

/** The selected scope — the slice of a workspace we persist and send.
 *  `view` distinguishes the two faces of a developer workspace: the internal
 *  knowledge base (default) and the developer console chrome. */
export type Scope = Pick<Workspace, "scope_user_id" | "name"> & {
  view?: "developer";
};

/** Filter-chip counts, computed over the whole table rather than a loaded
 *  page — a chip whose count reflects page one is worse than no chip. */
export interface AppFacets {
  total: number;
  topics: { label: string; count: number }[];
  untagged: number;
  duplicates: number;
  broken: number;
}

// ── Reward model platform (/api/v1/rm) ────────────────────────────────────
// Shapes follow docs/reward-models/DESIGN.md.

export type RmRole = "system" | "user" | "assistant" | "tool";
export type RmJobStatus = "queued" | "running" | "succeeded" | "failed";
export type RmCompute = "local" | "modal";

export interface RmFormat {
  name: string;
  description: string;
}

export interface RmImportResult {
  format: string;
  imported: number;
  trace_ids: string[];
}

export interface RmScore {
  reward_model_id: string;
  reward_model_name: string;
  score: number;
  created_at: string;
}

export interface RmTraceSummary {
  can_score?: boolean;
  agent?: string;
  source_id?: string;
  source_name?: string;
  source_owner_id?: string;
  id: string;
  external_id: string | null;
  title: string;
  source_format: string;
  step_count: number;
  positive_count: number;
  negative_count: number;
  comment_count: number;
  label_error_count: number;
  latest_score: Omit<RmScore, "created_at"> | null;
  shared_training_allowed?: boolean;
  evaluation?: { id: string; status: string; outcome: string | null; current: boolean; score?: number | null; action_credit?: { mean: number; min: number; max: number; count: number } | null; total_actions: number; credited_actions: number } | null;
  action_credit?: { mean: number; min?: number; max?: number; count: number; revision: number | null } | null;
  workbench?: {
    assessed_actions: number;
    total_actions: number;
    violations: number;
    pending: number;
    failed: number;
    queue_status: string | null;
  };
  created_at: string;
}

export interface RmTraceImage {
  id: string;
  start: number;
  end: number;
  width: number;
  height: number;
}

export interface RmStep {
  id: string;
  index: number;
  role: RmRole;
  content: string;
  tool_name: string | null;
  tool_input: Record<string, unknown> | null;
  tool_call_id: string | null;
  metadata: Record<string, unknown> | null;
  images?: RmTraceImage[];
}

/** The highlighted span inside a step's content, anchored by surrounding text. */
export interface RmQuote {
  text: string;
  prefix: string;
  suffix: string;
  /** One anchor per message for a selection spanning multiple messages. */
  segments?: (Omit<RmQuote, "segments"> & { step_id: string })[];
}

export interface RmAnnotation {
  id: string;
  trace_id: string;
  step_id: string | null;
  rating: 1 | -1 | null;
  comment: string | null;
  quote: RmQuote | null;
  label_error: boolean;
  label_error_note: string | null;
  author_id: string;
  author_name: string;
  created_at: string;
}

export interface RmTraceSpan {
  id: string;
  parent_id: string | null;
  name: string;
  kind: string | null;
  start_ns: string;
  end_ns: string;
  input: string | null;
  output: string | null;
  step_indices: number[];
}

export interface RmTraceDetail extends RmTraceSummary {
  training_models?: Pick<RmRewardModel, "id" | "name" | "status" | "error" | "created_at" | "finished_at">[];
  /** Task scores from the step-scoring rules; the per-step scores are on each step's `metadata.reward`. */
  step_scores?: unknown;
  automatic_evaluation?: import("./workbench-api").TraceEvaluationResponse;
  spans: RmTraceSpan[];
  metadata: Record<string, unknown> | null;
  steps: RmStep[];
  annotations: RmAnnotation[];
  scores: RmScore[];
  action_scores?: RmActionScore[];
  scoring_runs?: RmScoringRun[];
  default_evaluator?: { id: string; name: string; revision: number; updated_at: string } | null;
  automatic_scoring?: { attempts: number; error: string | null } | null;
  training_collection?: { status: RmJobStatus; error: string | null } | null;
}

export interface RmActionScore {
  /** Display-only automatic annotation from an earlier trace revision. */
  stale?: boolean;
  reward_model_id: string;
  reward_model_name: string;
  step_id: string;
  score: number;
  /** Training-reference relative reward in [-1, 1], not a probability. */
  credit: number;
  created_at: string;
}

export interface RmScoringRun {
  id: string;
  trace_id: string;
  reward_model_id: string;
  status: RmJobStatus;
  error: string | null;
}

export interface RmTrainMetrics {
  train_pairs: number;
  eval_pairs: number;
  eval_accuracy: number | null;
  eval_split?: "trace" | "curated_task_groups";
  action_scoring_version?: number | null;
  trace_scoring_version?: number | null;
  action_train_pairs?: number;
  action_eval_pairs?: number;
  action_eval_accuracy?: number | null;
  tool_eval_pairs?: number;
  tool_eval_accuracy?: number | null;
  final_loss: number;
  epochs: number;
  device: string;
  seconds: number;
}

export interface RmRewardModel {
  id: string;
  name: string;
  base_model: string;
  compute: RmCompute;
  epochs: number;
  status: RmJobStatus;
  num_pairs: number | null;
  /** How many traces the user picked to train on. */
  trace_count: number;
  metrics: RmTrainMetrics | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress?: {
    stage: "preparing" | "starting" | "loading" | "training" | "evaluating" | "scoring" | "uploading";
    completed: number;
    total: number;
    elapsed_seconds: number;
    updated_at: string;
  } | null;
  estimated_timing?: {
    basis: "history" | "batches";
    scope: "job" | "training";
    sample_count: number;
    lower_seconds: number;
    upper_seconds: number;
    overdue: boolean;
    excludes_queue: boolean;
  } | null;
}

/** GET /reward-models/{id} also returns which traces it trained on. */
export interface RmRewardModelDetail extends RmRewardModel {
  trace_ids: string[];
  feedback: RmInferredFeedback[] | null;
}

export interface RmInferredFeedback {
  source: "user_feedback" | "ai_judgment";
  trace_id: string;
  step_index: number;
  tool_name?: string | null;
  label: "positive" | "negative" | "unclear";
  confidence: "high" | "low";
  evidence_id: string;
  evidence_quote: string;
  reason: string;
  classifier_model: string;
  included_in_training: boolean;
  included_in_evaluation?: boolean;
  original_action?: string;
  alternative_action?: string | null;
}

export interface RmGepaCandidate {
  /** The full rendered SKILL.md. */
  skill: string;
  score: number;
}

export interface RmGepaRun {
  id: string;
  reward_model_id: string;
  /** Written by the run; null until it succeeds. */
  skill_name: string | null;
  skill_description: string | null;
  task_model: string;
  task_api_base: string | null;
  reflection_model: string;
  max_metric_calls: number;
  status: RmJobStatus;
  error: string | null;
  seed_skill: string | null;
  best_skill: string | null;
  seed_score: number | null;
  best_score: number | null;
  candidates: RmGepaCandidate[] | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}


export interface RmPlaygroundInput {
  prompt?: string;
  instructions?: string;
  responses?: string[];
  example_index?: number;
  texts?: string[];
}

export interface RmPlaygroundRun {
  id: string;
  reward_model_id: string;
  status: RmJobStatus;
  input: RmPlaygroundInput;
  scores: number[] | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface RmPlaygroundHistory {
  items: (Pick<RmPlaygroundRun, "id" | "status" | "scores" | "error" | "created_at"> & {
    prompt: string | null; example_index: string | null;
  })[];
  total: number;
}

export interface RmTrainingExample {
  index: number;
  chosen: string;
  rejected: string;
  partition: string | null;
  source: string | null;
  trace_ids: string[];
}
