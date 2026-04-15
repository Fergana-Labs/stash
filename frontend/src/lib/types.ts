export interface User {
  id: string;
  name: string;
  display_name: string | null;
  description: string;
  created_at: string;
  last_seen: string;
}

export interface RegisterResponse {
  id: string;
  name: string;
  display_name: string | null;
  api_key: string;
}

// --- Workspaces ---

export interface Workspace {
  id: string;
  name: string;
  description: string;
  creator_id: string;
  invite_code: string;
  is_public: boolean;
  created_at: string;
  updated_at: string;
  member_count: number | null;
}

export interface WorkspaceMember {
  user_id: string;
  name: string;
  display_name: string | null;
  role: string;
  joined_at: string;
}

// --- Notebooks (collections) ---

export interface Notebook {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface NotebookPage {
  id: string;
  notebook_id: string;
  folder_id: string | null;
  name: string;
  content_markdown: string;
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotebookFolder {
  id: string;
  notebook_id: string;
  name: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PageTreeFile {
  id: string;
  name: string;
  folder_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PageTreeFolder {
  id: string;
  name: string;
  files: PageTreeFile[];
  created_at: string;
}

export interface PageTree {
  folders: PageTreeFolder[];
  root_files: PageTreeFile[];
}

// --- History ---

export interface History {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
  event_count: number | null;
}

export interface HistoryEvent {
  id: string;
  store_id: string;
  agent_name: string;
  event_type: string;
  session_id: string | null;
  tool_name: string | null;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface HistoryWithWorkspace extends History {
  workspace_name: string | null;
}

export interface HistoryEventWithContext extends HistoryEvent {
  store_name: string;
  workspace_id: string | null;
  workspace_name: string | null;
}

// --- Permissions ---

export interface ObjectPermission {
  object_type: string;
  object_id: string;
  visibility: "inherit" | "private" | "public";
  shares: Share[];
}

export interface Share {
  user_id: string;
  user_name: string;
  permission: "read" | "write" | "admin";
  granted_by: string;
  created_at: string;
}

// --- Tables ---

export interface TableColumn {
  id: string;
  name: string;
  type: "text" | "number" | "boolean" | "date" | "datetime" | "url" | "email" | "select" | "multiselect" | "json";
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

export interface NotebookWithWorkspace extends Notebook {
  workspace_name: string | null;
}

// --- Files ---

export interface FileInfo {
  id: string;
  workspace_id: string | null;
  name: string;
  content_type: string;
  size_bytes: number;
  url: string;
  uploaded_by: string;
  created_at: string;
}

export interface Attachment {
  file_id: string;
  name: string;
  content_type: string;
}

// --- Wiki / Page Links ---

export interface PageLink {
  id: string;
  name: string;
  notebook_id: string;
  link_text: string;
  created_at: string;
}

export interface PageGraph {
  nodes: { id: string; name: string }[];
  edges: { source: string; target: string; label: string }[];
}

// --- Dashboard Visualizations ---

export interface ActivityTimeline {
  agents: string[];
  buckets: {
    date: string;
    agents: Record<string, { total: number; by_type: Record<string, number> }>;
  }[];
}

export interface KnowledgeDensity {
  clusters: {
    label: string;
    count: number;
    sources: { notebook_pages: number; table_rows: number };
    newest_at: string | null;
    oldest_at: string | null;
    sample_titles: string[];
  }[];
}

export interface EmbeddingProjectionPoint {
  id: string;
  x: number;
  y: number;
  z: number;
  source: "notebook_pages" | "table_rows" | "history_events";
  label: string;
  created_at: string | null;
}

export interface EmbeddingProjection {
  points: EmbeddingProjectionPoint[];
  stats: { total_embeddings: number; projected: number };
  cached: boolean;
}

// --- Search ---

export interface UserSearchResult {
  id: string;
  name: string;
  display_name: string | null;
}
