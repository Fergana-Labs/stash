import {
  CommentThread,
  FileInfo,
  Folder,
  Page,
  WorkspaceTree,
  RegisterResponse,
  User,
  UserSearchResult,
  Table,
  TableRow,
  TableWithWorkspace,
  Workspace,
  WorkspaceMember,
  ActivityTimeline,
  KnowledgeDensity,
  EmbeddingProjection,
} from "./types";

const TOKEN_KEY = "stash_token";
const API_BASE = "";

// --- Token management (for CLI API key fallback) ---

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export async function fetchAuthed(path: string): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(`${API_BASE}${path}`, { headers });
}

// Scope = workspace-scoped when workspaceId is set, personal otherwise.
// Used everywhere a resource has both /api/v1/workspaces/{ws}/... and /api/v1/... variants.
function scope(workspaceId: string | null): string {
  if (workspaceId) return `/api/v1/workspaces/${workspaceId}`;
  return "/api/v1";
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = body.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail) && detail[0]?.msg
        ? String(detail[0].msg)
        : `API error ${res.status}`;
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// --- Users ---

export async function register(
  name: string,
  displayName?: string,
  description?: string,
  password?: string
): Promise<RegisterResponse> {
  return apiFetch("/api/v1/users/register", {
    method: "POST",
    body: JSON.stringify({
      name,
      display_name: displayName || name,
      description: description || "",
      ...(password ? { password } : {}),
    }),
  });
}

export async function loginWithPassword(
  name: string,
  password: string
): Promise<RegisterResponse> {
  return apiFetch("/api/v1/users/login", {
    method: "POST",
    body: JSON.stringify({ name, password }),
  });
}

export async function getMe(): Promise<User> {
  return apiFetch("/api/v1/users/me");
}

export async function updateMe(data: {
  display_name?: string;
  description?: string;
  password?: string;
  current_password?: string;
}): Promise<User> {
  return apiFetch("/api/v1/users/me", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
}

export async function listMyKeys(): Promise<ApiKeyInfo[]> {
  return apiFetch("/api/v1/users/me/keys");
}

export async function revokeMyKey(keyId: string): Promise<void> {
  await apiFetch(`/api/v1/users/me/keys/${keyId}`, { method: "DELETE" });
}

export interface ApiKeyCreated {
  id: string;
  name: string;
  api_key: string; // raw key — shown exactly once
  created_at: string;
}

export async function createMyKey(name: string): Promise<ApiKeyCreated> {
  return apiFetch("/api/v1/users/me/keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function searchUsers(query: string): Promise<UserSearchResult[]> {
  return apiFetch(`/api/v1/users/search?q=${encodeURIComponent(query)}`);
}

// --- Workspaces ---

export async function createWorkspace(name: string, description?: string): Promise<Workspace> {
  return apiFetch("/api/v1/workspaces", {
    method: "POST",
    body: JSON.stringify({
      name,
      description: description || "",
    }),
  });
}

export async function listMyWorkspaces(): Promise<{ workspaces: Workspace[] }> {
  return apiFetch("/api/v1/workspaces/mine");
}

export async function getWorkspace(workspaceId: string): Promise<Workspace> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}`);
}

export async function joinWorkspace(inviteCode: string): Promise<Workspace> {
  return apiFetch(`/api/v1/workspaces/join/${inviteCode}`, { method: "POST" });
}

export async function createInviteToken(
  workspaceId: string,
  maxUses = 5,
  ttlDays = 7
): Promise<{ id: string; token: string; workspace_id: string; expires_at: string }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/invite-tokens`, {
    method: "POST",
    body: JSON.stringify({ max_uses: maxUses, ttl_days: ttlDays }),
  });
}

export async function rotateWorkspaceInvite(workspaceId: string): Promise<Workspace> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/invite-code/rotate`, { method: "POST" });
}

export async function leaveWorkspace(workspaceId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/leave`, { method: "POST" });
}

export async function getWorkspaceMembers(workspaceId: string): Promise<WorkspaceMember[]> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/members`);
}

export async function updateWorkspace(
  workspaceId: string,
  data: {
    name?: string;
    description?: string;
    cover_image_url?: string | null;
    icon_url?: string | null;
    color_gradient?: string | null;
  }
): Promise<Workspace> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}`, { method: "DELETE" });
}

export async function kickWorkspaceMember(workspaceId: string, userId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/kick/${userId}`, { method: "POST" });
}

export async function setWorkspaceMemberRole(
  workspaceId: string,
  userId: string,
  role: "owner" | "editor" | "viewer"
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/members/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
}

// --- Discover (public catalog, no auth required) ---

export interface PublicStashCard {
  id: string;
  slug: string;
  title: string;
  description: string;
  discoverable: boolean;
  cover_image_url: string | null;
  view_count: number;
  owner_name: string;
  owner_display_name: string | null;
  workspace_id: string;
  workspace_name: string;
  item_count: number;
  created_at: string;
  updated_at: string;
}

// --- Files: folders (nested) and pages ---

export async function getWorkspaceTree(workspaceId: string): Promise<WorkspaceTree> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/tree`);
}

export async function listFolders(workspaceId: string): Promise<{ folders: Folder[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/folders`);
}

export async function createFolder(
  workspaceId: string,
  name: string,
  parentFolderId?: string | null
): Promise<Folder> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/folders`, {
    method: "POST",
    body: JSON.stringify({
      name,
      parent_folder_id: parentFolderId || null,
    }),
  });
}

export async function updateFolder(
  workspaceId: string,
  folderId: string,
  data: { name?: string; parent_folder_id?: string | null; move_to_root?: boolean }
): Promise<Folder> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/folders/${folderId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteFolder(
  workspaceId: string,
  folderId: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/folders/${folderId}`, { method: "DELETE" });
}

export async function createPage(
  workspaceId: string,
  name: string,
  folderId?: string | null,
  content?: string,
  options?: {
    content_type?: "markdown" | "html";
    content_html?: string;
    html_layout?: "responsive" | "fixed-aspect";
  }
): Promise<Page> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/pages/new`, {
    method: "POST",
    body: JSON.stringify({
      name,
      folder_id: folderId || null,
      content: content || "",
      content_type: options?.content_type ?? "markdown",
      content_html: options?.content_html ?? "",
      html_layout: options?.html_layout ?? "responsive",
    }),
  });
}

export async function getPage(workspaceId: string, pageId: string): Promise<Page> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/pages/${pageId}`);
}

export async function updatePage(
  workspaceId: string,
  pageId: string,
  data: {
    name?: string;
    folder_id?: string | null;
    content?: string;
    content_type?: "markdown" | "html";
    content_html?: string;
    html_layout?: "responsive" | "fixed-aspect";
    move_to_root?: boolean;
  }
): Promise<Page> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/pages/${pageId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deletePage(workspaceId: string, pageId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/pages/${pageId}`, { method: "DELETE" });
}

// --- Page comments ---

export async function listCommentThreads(
  workspaceId: string,
  pageId: string,
): Promise<{ threads: CommentThread[] }> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}/comments/threads`,
  );
}

export async function createCommentThread(
  workspaceId: string,
  pageId: string,
  data: { quoted_text: string; prefix: string; suffix: string; body: string },
): Promise<CommentThread> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}/comments/threads`,
    { method: "POST", body: JSON.stringify(data) },
  );
}

export async function replyToCommentThread(
  workspaceId: string,
  pageId: string,
  threadId: string,
  body: string,
): Promise<CommentThread> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}/comments/threads/${threadId}/messages`,
    { method: "POST", body: JSON.stringify({ body }) },
  );
}

export async function setCommentResolved(
  workspaceId: string,
  pageId: string,
  threadId: string,
  resolved: boolean,
): Promise<CommentThread> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}/comments/threads/${threadId}`,
    { method: "PATCH", body: JSON.stringify({ resolved }) },
  );
}

export async function reconcileCommentAnchors(
  workspaceId: string,
  pageId: string,
  presentIds: string[],
): Promise<void> {
  await apiFetch(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}/comments/reconcile`,
    { method: "POST", body: JSON.stringify({ present_ids: presentIds }) },
  );
}

// --- Aggregate (cross-workspace) ---

// Cross-workspace flat page list for page pickers and search surfaces.
export async function listAllPages(): Promise<{ pages: UserPageEntry[] }> {
  return apiFetch("/api/v1/me/pages");
}

export interface UserPageEntry {
  id: string;
  name: string;
  workspace_id: string;
  folder_id: string | null;
  folder_path: string[];
  workspace_name: string;
  updated_at: string;
}

export async function listAllTables(): Promise<{ tables: TableWithWorkspace[] }> {
  return apiFetch("/api/v1/me/tables");
}

// --- Dashboard Visualizations ---

export async function getActivityTimeline(
  days = 30, bucket = "day", workspaceId?: string | null
): Promise<ActivityTimeline> {
  const ws = workspaceId ? `&workspace_id=${workspaceId}` : "";
  return apiFetch(`/api/v1/me/activity-timeline?days=${days}&bucket=${bucket}${ws}`);
}

export async function getKnowledgeDensity(
  maxClusters = 20, workspaceId?: string | null
): Promise<KnowledgeDensity> {
  const ws = workspaceId ? `&workspace_id=${workspaceId}` : "";
  return apiFetch(`/api/v1/me/knowledge-density?max_clusters=${maxClusters}${ws}`);
}

export async function getEmbeddingProjection(
  maxPoints = 500, source?: string, workspaceId?: string | null
): Promise<EmbeddingProjection> {
  const src = source ? `&source=${source}` : "";
  const ws = workspaceId ? `&workspace_id=${workspaceId}` : "";
  return apiFetch(`/api/v1/me/embedding-projection?max_points=${maxPoints}${src}${ws}`);
}

// --- Tables ---

export async function createTable(
  workspaceId: string | null,
  name: string,
  description?: string,
  columns?: { name: string; type: string; options?: string[] }[]
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || "", columns: columns || [] }),
  });
}

export async function listTables(
  workspaceId: string | null
): Promise<{ tables: Table[] }> {
  return apiFetch(`${scope(workspaceId)}/tables`);
}

export async function getTable(
  workspaceId: string | null,
  tableId: string
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}`);
}

export async function updateTable(
  workspaceId: string | null,
  tableId: string,
  data: { name?: string; description?: string }
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}`, {
    method: "PATCH", body: JSON.stringify(data),
  });
}

export async function deleteTable(
  workspaceId: string | null,
  tableId: string
): Promise<void> {
  await apiFetch(`${scope(workspaceId)}/tables/${tableId}`, { method: "DELETE" });
}

// --- Table Columns ---

export async function addTableColumn(
  workspaceId: string | null,
  tableId: string,
  column: { name: string; type: string; required?: boolean; default?: unknown; options?: string[] }
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/columns`, {
    method: "POST", body: JSON.stringify(column),
  });
}

export async function updateTableColumn(
  workspaceId: string | null,
  tableId: string,
  columnId: string,
  updates: { name?: string; type?: string; required?: boolean; default?: unknown; options?: string[] }
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/columns/${columnId}`, {
    method: "PATCH", body: JSON.stringify(updates),
  });
}

export async function deleteTableColumn(
  workspaceId: string | null,
  tableId: string,
  columnId: string
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/columns/${columnId}`, { method: "DELETE" });
}

export async function reorderTableColumns(
  workspaceId: string | null,
  tableId: string,
  columnIds: string[]
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/columns/reorder`, {
    method: "PUT", body: JSON.stringify({ column_ids: columnIds }),
  });
}

// --- Table Rows ---

export async function listTableRows(
  workspaceId: string | null,
  tableId: string,
  params?: { sort_by?: string; sort_order?: string; limit?: number; offset?: number; filters?: object[] }
): Promise<{ rows: TableRow[]; total_count: number; has_more: boolean }> {
  const query = new URLSearchParams();
  if (params?.sort_by) query.set("sort_by", params.sort_by);
  if (params?.sort_order) query.set("sort_order", params.sort_order);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  if (params?.filters) query.set("filters", JSON.stringify(params.filters));
  const qs = query.toString();
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/rows${qs ? "?" + qs : ""}`);
}

export async function createTableRow(
  workspaceId: string | null,
  tableId: string,
  data: Record<string, unknown>
): Promise<TableRow> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/rows`, {
    method: "POST", body: JSON.stringify({ data }),
  });
}

export async function createTableRowsBatch(
  workspaceId: string | null,
  tableId: string,
  rows: { data: Record<string, unknown> }[]
): Promise<{ rows: TableRow[] }> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/rows/batch`, {
    method: "POST", body: JSON.stringify({ rows }),
  });
}

export async function updateTableRow(
  workspaceId: string | null,
  tableId: string,
  rowId: string,
  data: Record<string, unknown>
): Promise<TableRow> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/rows/${rowId}`, {
    method: "PATCH", body: JSON.stringify({ data }),
  });
}

export async function deleteTableRow(
  workspaceId: string | null,
  tableId: string,
  rowId: string
): Promise<void> {
  await apiFetch(`${scope(workspaceId)}/tables/${tableId}/rows/${rowId}`, { method: "DELETE" });
}

export async function deleteTableRowsBatch(
  workspaceId: string | null,
  tableId: string,
  rowIds: string[]
): Promise<{ deleted: number }> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/rows/delete`, {
    method: "POST", body: JSON.stringify({ row_ids: rowIds }),
  });
}

// --- Table Search, Summary, Duplicate ---

export async function searchTableRows(
  workspaceId: string | null,
  tableId: string,
  query: string,
  params?: { limit?: number; offset?: number }
): Promise<{ rows: TableRow[]; total_count: number; has_more: boolean }> {
  const qs = new URLSearchParams({ q: query });
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/rows/search?${qs}`);
}

export async function summarizeTableRows(
  workspaceId: string | null,
  tableId: string,
  filters?: object[]
): Promise<{ total_rows: number; columns: Record<string, { name: string; filled: number; sum?: number; avg?: number; min?: number; max?: number }> }> {
  const qs = new URLSearchParams();
  if (filters && filters.length > 0) qs.set("filters", JSON.stringify(filters));
  const qsStr = qs.toString();
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/rows/summary${qsStr ? "?" + qsStr : ""}`);
}

export async function duplicateTableRow(
  workspaceId: string | null,
  tableId: string,
  rowId: string
): Promise<TableRow> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/rows/${rowId}/duplicate`, { method: "POST" });
}

// --- Table Views ---

export async function saveTableView(
  workspaceId: string | null,
  tableId: string,
  layout: { id?: string; name: string; filters?: object[]; sort_by?: string; sort_order?: string; visible_columns?: string[] }
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/views`, {
    method: "POST", body: JSON.stringify(layout),
  });
}

export async function deleteTableView(
  workspaceId: string | null,
  tableId: string,
  viewId: string
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/views/${viewId}`, { method: "DELETE" });
}

// --- Files ---

export async function uploadFile(
  workspaceId: string,
  file: File,
  folderId?: string | null
): Promise<FileInfo> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);
  if (folderId) formData.append("folder_id", folderId);
  const resp = await fetch(
    `${API_BASE}/api/v1/workspaces/${workspaceId}/files`,
    {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    }
  );
  if (!resp.ok) {
    const detail = await resp.json().then((d) => d.detail).catch(() => resp.statusText);
    throw new Error(detail);
  }
  return resp.json();
}

export async function listFiles(workspaceId: string): Promise<FileInfo[]> {
  const data = await apiFetch<{ files: FileInfo[] }>(`/api/v1/workspaces/${workspaceId}/files`);
  return data.files;
}

export async function getFile(workspaceId: string, fileId: string): Promise<FileInfo> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}`);
}

export async function ingestCsvFile(workspaceId: string, fileId: string): Promise<Table> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}/ingest-csv`, {
    method: "POST",
  });
}

export async function deleteFile(workspaceId: string, fileId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}`, { method: "DELETE" });
}

export async function updateFile(
  workspaceId: string,
  fileId: string,
  data: { folder_id?: string | null; move_to_root?: boolean; name?: string }
): Promise<FileInfo> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// --- Sessions ---

export interface SessionSummary {
  session_id: string;
  workspace_id: string | null;
  workspace_name: string | null;
  user_name: string | null;
  agent_name: string | null;
  event_count: number;
  started_at: string;
  last_event_at: string;
  first_prompt_preview: string | null;
}

export async function listMySessions(workspaceId?: string, limit = 50): Promise<SessionSummary[]> {
  const qs = new URLSearchParams();
  if (workspaceId) qs.set("workspace_id", workspaceId);
  qs.set("limit", String(limit));
  const data = await apiFetch<{ sessions: SessionSummary[] }>(
    `/api/v1/me/sessions?${qs.toString()}`
  );
  return data.sessions;
}

export interface MaterializedSession {
  page: { id: string; workspace_id: string; folder_id: string | null; name: string };
  folder_id: string;
}

export interface SessionArtifact {
  id: string;
  file_path: string;
  size_bytes: number;
  url: string;
  created_at: string;
}

export interface SessionDetail {
  id: string;
  workspace_id: string;
  session_id: string;
  agent_name: string;
  cwd: string | null;
  summary: string | null;
  summary_status: string | null;
  files_touched: string[] | string;
  started_at: string | null;
  finished_at: string | null;
  created_by: string | null;
  artifacts: SessionArtifact[];
}

export async function getSessionDetail(
  workspaceId: string,
  sessionId: string
): Promise<SessionDetail> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/sessions/${encodeURIComponent(sessionId)}`);
}

export async function materializeSession(
  workspaceId: string,
  sessionId: string
): Promise<MaterializedSession> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/materialize`, {
    method: "POST",
  });
}

// --- Stashes (publishable bundles of pages, sessions, and files) ---

export type CollectableObjectType = "folder" | "page" | "table" | "file" | "session";

export interface StashItemSpec {
  object_type: CollectableObjectType;
  object_id: string;
  position?: number;
  label_override?: string | null;
}

export interface CreatedStash {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string;
  owner_id: string;
  access: "workspace" | "private" | "public";
  discoverable: boolean;
  cover_image_url: string | null;
  icon_url: string | null;
  view_count: number;
  items: StashItemSpec[];
  is_external: boolean;
  added_to_workspace_id: string | null;
  forked_from_stash_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublishedStashResult {
  stash: CreatedStash;
  url: string;
  stash_id: string;
  stash_slug: string;
}

export async function createStash(
  workspaceId: string,
  title: string,
  items: StashItemSpec[],
  opts: { description?: string; access?: "workspace" | "private" | "public"; discoverable?: boolean } = {}
): Promise<CreatedStash> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/stashes`, {
    method: "POST",
    body: JSON.stringify({
      title,
      description: opts.description ?? "",
      access: opts.access ?? "workspace",
      discoverable: opts.discoverable ?? false,
      cover_image_url: null,
      items: items.map((it, i) => ({
        object_type: it.object_type,
        object_id: it.object_id,
        position: it.position ?? i,
        label_override: it.label_override ?? null,
      })),
    }),
  });
}

export async function publishStash(
  workspaceId: string,
  title: string,
  items: StashItemSpec[],
  opts: { description?: string; discoverable?: boolean } = {}
): Promise<PublishedStashResult> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/stashes/publish`, {
    method: "POST",
    body: JSON.stringify({
      title,
      description: opts.description ?? "",
      access: "public",
      discoverable: opts.discoverable ?? false,
      cover_image_url: null,
      items: items.map((it, i) => ({
        object_type: it.object_type,
        object_id: it.object_id,
        position: it.position ?? i,
        label_override: it.label_override ?? null,
      })),
    }),
  });
}

export interface WorkspaceStash {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string;
  owner_id: string;
  access: "workspace" | "private" | "public";
  discoverable: boolean;
  cover_image_url: string | null;
  icon_url: string | null;
  view_count: number;
  items: StashItemSpec[];
  is_external: boolean;
  added_to_workspace_id: string | null;
  forked_from_stash_id: string | null;
  created_at: string;
  updated_at: string;
}

export type StashMemberPermission = "read" | "write" | "admin";

export interface StashMember {
  user_id: string;
  name: string;
  display_name: string | null;
  permission: StashMemberPermission;
  granted_by: string | null;
  created_at: string;
}

export interface PublicStashItem {
  object_type: CollectableObjectType;
  object_id: string;
  position: number;
  label: string;
  inline: Record<string, unknown>;
}

export interface PublicStashDetail {
  stash: WorkspaceStash;
  workspace_name: string;
  items: PublicStashItem[];
  can_write: boolean;
}

export async function listStashes(workspaceId: string): Promise<WorkspaceStash[]> {
  const data = await apiFetch<{ stashes: WorkspaceStash[] }>(
    `/api/v1/workspaces/${workspaceId}/stashes`
  );
  return data.stashes;
}

export async function listObjectStashes(
  workspaceId: string,
  objectType: CollectableObjectType,
  objectId: string
): Promise<WorkspaceStash[]> {
  const data = await apiFetch<{ stashes: WorkspaceStash[] }>(
    `/api/v1/workspaces/${workspaceId}/stashes/objects/${objectType}/${objectId}`
  );
  return data.stashes;
}

export async function deleteStash(stashId: string): Promise<void> {
  await apiFetch(`/api/v1/stashes/${stashId}`, { method: "DELETE" });
}

export async function updateStash(
  stashId: string,
  data: {
    title?: string;
    description?: string;
    access?: "workspace" | "private" | "public";
    discoverable?: boolean;
    cover_image_url?: string | null;
    icon_url?: string | null;
    items?: StashItemSpec[];
  }
): Promise<WorkspaceStash> {
  return apiFetch(`/api/v1/stashes/${stashId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function listStashMembers(stashId: string): Promise<StashMember[]> {
  const data = await apiFetch<{ members: StashMember[] }>(
    `/api/v1/stashes/${stashId}/members`
  );
  return data.members;
}

export async function addStashMember(
  stashId: string,
  userId: string,
  permission: StashMemberPermission
): Promise<StashMember> {
  return apiFetch(`/api/v1/stashes/${stashId}/members`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, permission }),
  });
}

export async function removeStashMember(stashId: string, userId: string): Promise<void> {
  await apiFetch(`/api/v1/stashes/${stashId}/members/${userId}`, { method: "DELETE" });
}

export async function getPublicStash(slug: string): Promise<PublicStashDetail> {
  return apiFetch(`/api/v1/stashes/${slug}`);
}

export async function createSharedStashPage(
  stashId: string,
  data: {
    name: string;
    content: string;
    content_type?: "markdown" | "html";
    content_html?: string;
    html_layout?: "responsive" | "fixed-aspect";
  }
): Promise<Page> {
  return apiFetch(`/api/v1/stashes/${stashId}/shared-pages`, {
    method: "POST",
    body: JSON.stringify({
      name: data.name,
      content: data.content,
      content_type: data.content_type ?? "markdown",
      content_html: data.content_html ?? "",
      html_layout: data.html_layout ?? "responsive",
    }),
  });
}

export async function addExternalStash(
  slug: string,
  workspaceId: string
): Promise<WorkspaceStash> {
  return apiFetch(`/api/v1/stashes/${slug}/add-to-workspace`, {
    method: "POST",
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
}

export async function removeExternalStash(
  workspaceId: string,
  stashId: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/external-stashes/${stashId}`, {
    method: "DELETE",
  });
}

// --- Stash invites ---

export interface StashInvite {
  id: string;
  stash_id: string;
  stash_slug: string;
  stash_title: string;
  stash_description: string;
  source_workspace_id: string;
  source_workspace_name: string;
  invited_by_user_id: string;
  invited_by_name: string;
  invited_by_display_name: string | null;
  permission: StashMemberPermission;
  created_at: string;
}

export async function listStashInvites(): Promise<StashInvite[]> {
  const data = await apiFetch<{ invites: StashInvite[] }>("/api/v1/stash-invites");
  return data.invites;
}

export async function dismissStashInvite(inviteId: string): Promise<void> {
  await apiFetch(`/api/v1/stash-invites/${inviteId}/dismiss`, { method: "POST" });
}

// --- Workspace-wide page index ---

export interface WorkspacePageEntry {
  id: string;
  name: string;
  workspace_id: string;
  folder_id: string | null;
  // Chain of folder names from the workspace root down to the page's folder.
  // Empty for pages at the workspace root.
  folder_path: string[];
  updated_at: string;
}

export async function listWorkspacePages(
  workspaceId: string
): Promise<WorkspacePageEntry[]> {
  const data = await apiFetch<{ pages: WorkspacePageEntry[] }>(
    `/api/v1/workspaces/${workspaceId}/pages`
  );
  return data.pages;
}

// --- Page semantic search ---

export async function semanticSearchPages(
  workspaceId: string,
  query: string,
  limit = 20
): Promise<Page[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const data = await apiFetch<{ pages: Page[] }>(
    `/api/v1/workspaces/${workspaceId}/pages/semantic-search?${params}`
  );
  return data.pages;
}

export async function searchWorkspacePages(
  workspaceId: string,
  query: string,
  limit = 20
): Promise<Page[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const data = await apiFetch<{ pages: Page[] }>(
    `/api/v1/workspaces/${workspaceId}/pages/search?${params}`
  );
  return data.pages;
}

// --- Table Embeddings (workspace-only) ---

export async function setTableEmbeddingConfig(
  workspaceId: string,
  tableId: string,
  config: { enabled: boolean; columns: string[] }
): Promise<Table> {
  return apiFetch<Table>(`/api/v1/workspaces/${workspaceId}/tables/${tableId}/embedding`, {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export async function backfillTableEmbeddings(
  workspaceId: string,
  tableId: string
): Promise<{ embedded: number; total: number }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/tables/${tableId}/embedding/backfill`, {
    method: "POST",
  });
}

export async function semanticSearchTableRows(
  workspaceId: string,
  tableId: string,
  query: string,
  limit = 20
): Promise<TableRow[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const data = await apiFetch<{ rows: TableRow[] }>(
    `/api/v1/workspaces/${workspaceId}/tables/${tableId}/rows/semantic-search?${params}`
  );
  return data.rows;
}

// --- Agent Names ---

export async function listAgentNames(workspaceId: string): Promise<string[]> {
  const data = await apiFetch<{ agent_names: string[] }>(
    `/api/v1/workspaces/${workspaceId}/sessions/agent-names`
  );
  return data.agent_names;
}

// --- Activity feed ---

export interface ActivityEvent {
  kind: string;
  ts: string;
  actor: { name: string; display_name: string | null };
  target_id: string;
  target_label: string;
  workspace_id?: string;
  workspace_name?: string;
}

export async function listActivity(limit = 100): Promise<ActivityEvent[]> {
  return apiFetch(`/api/v1/me/activity?limit=${limit}`);
}

export async function listWorkspaceActivity(
  workspaceId: string,
  limit = 100
): Promise<ActivityEvent[]> {
  const qs = new URLSearchParams({
    limit: String(limit),
    workspace_id: workspaceId,
  });
  return apiFetch(`/api/v1/me/activity?${qs}`);
}

// --- Session transcripts ---

export interface SessionTranscript {
  id: string;
  workspace_id: string;
  session_id: string;
  agent_name: string;
  size_bytes: number;
  cwd: string | null;
  uploaded_by: string;
  uploaded_at: string;
  download_url: string | null;
}

export async function getWorkspaceTranscript(
  workspaceId: string,
  sessionId: string
): Promise<SessionTranscript> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/transcripts/${encodeURIComponent(sessionId)}`
  );
}

export interface SessionEvent {
  id: string;
  role: "user" | "assistant";
  agent_name: string;
  content: string;
  tool_name: string | null;
  created_at: string | null;
}

export async function getSessionEvents(
  workspaceId: string,
  sessionId: string
): Promise<SessionEvent[]> {
  const res = await apiFetch<{ events: SessionEvent[] }>(
    `/api/v1/workspaces/${workspaceId}/transcripts/${encodeURIComponent(sessionId)}/events`
  );
  return res.events;
}

export interface WorkspaceHistoryEvent {
  id: string;
  workspace_id: string;
  created_by: string;
  created_by_name: string | null;
  agent_name: string;
  event_type: string;
  session_id: string | null;
  tool_name: string | null;
  content: string;
  metadata: Record<string, unknown>;
  attachments: Record<string, unknown>[] | null;
  created_at: string;
  rank?: number | null;
}

export async function searchWorkspaceEvents(
  workspaceId: string,
  query: string,
  limit = 100
): Promise<WorkspaceHistoryEvent[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await apiFetch<{ events: WorkspaceHistoryEvent[] }>(
    `/api/v1/workspaces/${workspaceId}/sessions/events/search?${params}`
  );
  return res.events;
}

export interface UploadedTranscript {
  session_id: string;
  imported: number;
  skipped: boolean;
  reason?: string;
}

export async function uploadTranscript(
  workspaceId: string,
  file: File,
  sessionId: string,
  agentName: string,
  cwd?: string
): Promise<UploadedTranscript> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);
  formData.append("agent_name", agentName);
  if (cwd) formData.append("cwd", cwd);

  const resp = await fetch(`${API_BASE}/api/v1/workspaces/${workspaceId}/transcripts`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!resp.ok) {
    const detail = await resp.json().then((d) => d.detail).catch(() => resp.statusText);
    throw new Error(detail);
  }
  return resp.json();
}

// --- Workspace overview, sessions, files, and stashes ---

export interface WorkspaceSidebarSession {
  id: string | null;
  session_id: string;
  title: string;
  user_name: string | null;
  agent_name: string;
  size_bytes: number;
  last_at: string;
  updated_at: string;
}

// Unified Files tree. Folders, pages, and files
// each carry their parent so the frontend can build the hierarchy.
export interface WorkspaceFolder {
  id: string;
  name: string;
  parent_folder_id: string | null;
  page_count: number;
  file_count: number;
  has_skill: boolean;
}
export interface WorkspacePage {
  id: string;
  name: string;
  folder_id: string | null;
}
export interface WorkspaceFile {
  id: string;
  name: string;
  folder_id: string | null;
  size_bytes: number;
  content_type: string;
  url: string | null;
  created_at: string;
  linked_table_id?: string | null;
}
export interface WorkspaceFiles {
  folders: WorkspaceFolder[];
  pages: WorkspacePage[];
  files: WorkspaceFile[];
}

export interface WorkspaceSidebarStash {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string;
  access: "workspace" | "private" | "public";
  discoverable: boolean;
  is_external: boolean;
  forked_from_stash_id: string | null;
  item_count: number;
  items?: StashItemSpec[];
  updated_at: string;
}

export interface WorkspaceOverview {
  sessions: WorkspaceSidebarSession[];
  files: WorkspaceFiles;
  stashes?: WorkspaceSidebarStash[];
}

export async function getWorkspaceOverview(workspaceId: string): Promise<WorkspaceOverview> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/overview`);
}

export interface WorkspaceSidebar {
  sessions: WorkspaceSidebarSession[];
  files: WorkspaceFiles;
  stashes?: WorkspaceSidebarStash[];
}

// In-memory store for the last ETag seen per workspace, so navigating between
// workspaces hits the cached payload instead of refetching.
const _sidebarEtags: Record<string, string> = {};
const _sidebarCache: Record<string, WorkspaceSidebar> = {};

export async function getWorkspaceSidebar(workspaceId: string): Promise<WorkspaceSidebar> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const cached = _sidebarEtags[workspaceId];
  if (cached) headers["If-None-Match"] = cached;

  const res = await fetch(`${API_BASE}/api/v1/workspaces/${workspaceId}/sidebar`, {
    method: "GET",
    headers,
  });
  if (res.status === 304 && _sidebarCache[workspaceId]) return _sidebarCache[workspaceId];
  if (!res.ok) throw new ApiError(res.status, `sidebar fetch failed: ${res.status}`);
  const etag = res.headers.get("etag");
  if (etag) _sidebarEtags[workspaceId] = etag;
  const body = (await res.json()) as WorkspaceSidebar;
  _sidebarCache[workspaceId] = body;
  return body;
}

export interface FolderBreadcrumb {
  id: string;
  name: string;
}
export interface FolderSubfolder {
  id: string;
  name: string;
  page_count: number;
  file_count: number;
}
export interface FolderContents {
  folder: { id: string; name: string; parent_folder_id: string | null };
  breadcrumbs: FolderBreadcrumb[];
  subfolders: FolderSubfolder[];
  pages: { id: string; name: string }[];
  files: Omit<WorkspaceFile, "folder_id">[];
}

export async function getFolderContents(
  workspaceId: string,
  folderId: string
): Promise<FolderContents> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/folders/${folderId}/contents`
  );
}
