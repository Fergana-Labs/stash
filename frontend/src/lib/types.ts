export interface User {
  id: string;
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

/** A published skill an app's table is built for. Carries a slug because you
 *  may not hold it yet: the strip that lists these offers Add for those. */
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
  source: "pages" | "table_rows" | "sessions" | "files";
  label: string;
  /** For sessions: event count and agent, e.g. "12 events · claude". */
  detail?: string;
  created_at: string | null;
  cluster: number;
}

export interface EmbeddingProjectionCluster {
  index: number;
  name: string;
  size: number;
}

export interface EmbeddingProjection {
  points: EmbeddingProjectionPoint[];
  clusters: EmbeddingProjectionCluster[];
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
