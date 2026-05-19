export interface User {
  id: string;
  name: string;
  display_name: string;
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

// --- Workspaces ---

export interface Workspace {
  id: string;
  name: string;
  description: string;
  creator_id: string;
  invite_code: string;
  created_at: string;
  updated_at: string;
  member_count: number | null;
  cover_image_url?: string | null;
  icon_url?: string | null;
  color_gradient?: string | null;
}

export interface WorkspaceMember {
  user_id: string;
  name: string;
  display_name: string;
  role: string;
  joined_at: string;
}

// --- Files: folders (nested) and pages ---

export type PageContentType = "markdown" | "html";

export interface Folder {
  id: string;
  workspace_id: string;
  parent_folder_id: string | null;
  name: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export type HtmlLayout = "responsive" | "fixed-aspect";

export interface Page {
  id: string;
  workspace_id: string;
  folder_id: string | null;
  name: string;
  content_type: PageContentType;
  content_markdown: string;
  content_html: string;
  html_layout: HtmlLayout;
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
  workspace_id: string;
  folder_id: string | null;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface FolderTreeNode extends Folder {
  folders: FolderTreeNode[];
  pages: PageSummary[];
}

export interface WorkspaceTree {
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
}

export interface TableView {
  id: string;
  name: string;
  filters?: { column_id: string; op: string; value: string }[];
  sort_by?: string;
  sort_order?: string;
  visible_columns?: string[];
}

export interface Table {
  id: string;
  workspace_id: string | null;
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

export interface TableWithWorkspace extends Table {
  workspace_name: string | null;
}

// --- Files ---

export interface FileInfo {
  id: string;
  workspace_id: string | null;
  folder_id?: string | null;
  name: string;
  content_type: string;
  size_bytes: number;
  url: string;
  uploaded_by: string;
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
