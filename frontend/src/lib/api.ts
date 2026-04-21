import {
  FileInfo,
  HistoryEvent,
  HistoryEventWithContext,
  History,
  HistoryWithWorkspace,
  Notebook,
  NotebookFolder,
  NotebookPage,
  NotebookWithWorkspace,
  PageGraph,
  PageLink,
  PageTree,
  ObjectPermission,
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

export async function logoutServer(): Promise<void> {
  await apiFetch("/api/v1/users/logout", { method: "POST" });
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

export async function createWorkspace(
  name: string,
  description?: string,
  isPublic?: boolean
): Promise<Workspace> {
  return apiFetch("/api/v1/workspaces", {
    method: "POST",
    body: JSON.stringify({
      name,
      description: description || "",
      is_public: isPublic ?? false,
    }),
  });
}

export async function listPublicWorkspaces(): Promise<{ workspaces: Workspace[] }> {
  return apiFetch("/api/v1/workspaces");
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
  data: { name?: string; description?: string }
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

// --- Notebooks ---
// workspaceId = string for workspace-scoped, null for personal.

export async function listNotebooks(workspaceId: string | null): Promise<{ notebooks: Notebook[] }> {
  return apiFetch(`${scope(workspaceId)}/notebooks`);
}

export async function createNotebook(
  workspaceId: string | null,
  name: string,
  description?: string
): Promise<Notebook> {
  return apiFetch(`${scope(workspaceId)}/notebooks`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
}

export async function deleteNotebook(
  workspaceId: string | null,
  notebookId: string
): Promise<void> {
  await apiFetch(`${scope(workspaceId)}/notebooks/${notebookId}`, { method: "DELETE" });
}

// --- Notebook Pages ---

export async function listPageTree(
  workspaceId: string | null,
  notebookId: string
): Promise<PageTree> {
  return apiFetch(`${scope(workspaceId)}/notebooks/${notebookId}/pages`);
}

export async function createPage(
  workspaceId: string | null,
  notebookId: string,
  name: string,
  folderId?: string,
  content?: string
): Promise<NotebookPage> {
  return apiFetch(`${scope(workspaceId)}/notebooks/${notebookId}/pages`, {
    method: "POST",
    body: JSON.stringify({ name, folder_id: folderId || null, content: content || "" }),
  });
}

export async function getPage(
  workspaceId: string | null,
  notebookId: string,
  pageId: string
): Promise<NotebookPage> {
  return apiFetch(`${scope(workspaceId)}/notebooks/${notebookId}/pages/${pageId}`);
}

export async function updatePage(
  workspaceId: string | null,
  notebookId: string,
  pageId: string,
  data: { name?: string; folder_id?: string; content?: string; move_to_root?: boolean }
): Promise<NotebookPage> {
  return apiFetch(`${scope(workspaceId)}/notebooks/${notebookId}/pages/${pageId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deletePage(
  workspaceId: string | null,
  notebookId: string,
  pageId: string
): Promise<void> {
  await apiFetch(`${scope(workspaceId)}/notebooks/${notebookId}/pages/${pageId}`, { method: "DELETE" });
}

// --- Page Folders ---

export async function createPageFolder(
  workspaceId: string | null,
  notebookId: string,
  name: string
): Promise<NotebookFolder> {
  return apiFetch(`${scope(workspaceId)}/notebooks/${notebookId}/folders`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renamePageFolder(
  workspaceId: string | null,
  notebookId: string,
  folderId: string,
  name: string
): Promise<NotebookFolder> {
  return apiFetch(`${scope(workspaceId)}/notebooks/${notebookId}/folders/${folderId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deletePageFolder(
  workspaceId: string | null,
  notebookId: string,
  folderId: string
): Promise<void> {
  await apiFetch(`${scope(workspaceId)}/notebooks/${notebookId}/folders/${folderId}`, { method: "DELETE" });
}

// --- History ---

export async function createHistory(
  workspaceId: string | null,
  name: string,
  description?: string
): Promise<History> {
  return apiFetch(`${scope(workspaceId)}/memory`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
}

export async function listHistories(
  workspaceId: string | null
): Promise<{ stores: History[] }> {
  return apiFetch(`${scope(workspaceId)}/memory`);
}

export async function getHistory(
  workspaceId: string | null,
  storeId: string
): Promise<History> {
  return apiFetch(`${scope(workspaceId)}/memory/${storeId}`);
}

export async function deleteHistory(
  workspaceId: string | null,
  storeId: string
): Promise<void> {
  await apiFetch(`${scope(workspaceId)}/memory/${storeId}`, { method: "DELETE" });
}

export async function queryHistoryEvents(
  workspaceId: string | null,
  storeId: string,
  params?: {
    agent_name?: string;
    session_id?: string;
    event_type?: string;
    after?: string;
    before?: string;
    limit?: number;
  }
): Promise<{ events: HistoryEvent[]; has_more: boolean }> {
  const searchParams = new URLSearchParams();
  if (params?.agent_name) searchParams.set("agent_name", params.agent_name);
  if (params?.session_id) searchParams.set("session_id", params.session_id);
  if (params?.event_type) searchParams.set("event_type", params.event_type);
  if (params?.after) searchParams.set("after", params.after);
  if (params?.before) searchParams.set("before", params.before);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return apiFetch(`${scope(workspaceId)}/memory/${storeId}/events${qs ? `?${qs}` : ""}`);
}

export async function searchHistoryEvents(
  workspaceId: string | null,
  storeId: string,
  query: string,
  limit?: number
): Promise<{ events: HistoryEvent[]; has_more: boolean }> {
  const searchParams = new URLSearchParams({ q: query });
  if (limit) searchParams.set("limit", String(limit));
  return apiFetch(`${scope(workspaceId)}/memory/${storeId}/events/search?${searchParams.toString()}`);
}

// --- Aggregate (cross-workspace) ---

export async function listAllNotebooks(): Promise<{ notebooks: NotebookWithWorkspace[] }> {
  return apiFetch("/api/v1/me/notebooks");
}

export async function listAllHistories(): Promise<{ stores: HistoryWithWorkspace[] }> {
  return apiFetch("/api/v1/me/history");
}

export async function queryAllHistoryEvents(
  params?: {
    agent_name?: string;
    event_type?: string;
    after?: string;
    before?: string;
    limit?: number;
  }
): Promise<{ events: HistoryEventWithContext[]; has_more: boolean }> {
  const searchParams = new URLSearchParams();
  if (params?.agent_name) searchParams.set("agent_name", params.agent_name);
  if (params?.event_type) searchParams.set("event_type", params.event_type);
  if (params?.after) searchParams.set("after", params.after);
  if (params?.before) searchParams.set("before", params.before);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return apiFetch(`/api/v1/me/history-events${qs ? `?${qs}` : ""}`);
}

export async function queryWorkspaceHistoryEvents(
  workspaceId: string,
  params?: {
    agent_name?: string;
    session_id?: string;
    event_type?: string;
    after?: string;
    before?: string;
    limit?: number;
  }
): Promise<{ events: HistoryEvent[]; has_more: boolean }> {
  const searchParams = new URLSearchParams();
  if (params?.agent_name) searchParams.set("agent_name", params.agent_name);
  if (params?.session_id) searchParams.set("session_id", params.session_id);
  if (params?.event_type) searchParams.set("event_type", params.event_type);
  if (params?.after) searchParams.set("after", params.after);
  if (params?.before) searchParams.set("before", params.before);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return apiFetch(`/api/v1/workspaces/${workspaceId}/memory/events${qs ? `?${qs}` : ""}`);
}

export async function listAllTables(): Promise<{ tables: TableWithWorkspace[] }> {
  return apiFetch("/api/v1/me/tables");
}

// --- Dashboard Visualizations ---

export async function getActivityTimeline(
  days = 30, bucket = "day"
): Promise<ActivityTimeline> {
  return apiFetch(`/api/v1/me/activity-timeline?days=${days}&bucket=${bucket}`);
}

export async function getKnowledgeDensity(
  maxClusters = 20
): Promise<KnowledgeDensity> {
  return apiFetch(`/api/v1/me/knowledge-density?max_clusters=${maxClusters}`);
}

export async function getEmbeddingProjection(
  maxPoints = 500, source?: string
): Promise<EmbeddingProjection> {
  const qs = source ? `&source=${source}` : "";
  return apiFetch(`/api/v1/me/embedding-projection?max_points=${maxPoints}${qs}`);
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
  view: { id?: string; name: string; filters?: object[]; sort_by?: string; sort_order?: string; visible_columns?: string[] }
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/views`, {
    method: "POST", body: JSON.stringify(view),
  });
}

export async function deleteTableView(
  workspaceId: string | null,
  tableId: string,
  viewId: string
): Promise<Table> {
  return apiFetch(`${scope(workspaceId)}/tables/${tableId}/views/${viewId}`, { method: "DELETE" });
}

// --- Permissions (workspace-only) ---

export async function getPermissions(
  workspaceId: string,
  objectType: string,
  objectId: string
): Promise<ObjectPermission> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/${objectType}s/${objectId}/permissions`);
}

export async function setVisibility(
  workspaceId: string,
  objectType: string,
  objectId: string,
  visibility: "inherit" | "private" | "public"
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/${objectType}s/${objectId}/permissions`, {
    method: "PATCH",
    body: JSON.stringify({ visibility }),
  });
}

export async function addShare(
  workspaceId: string,
  objectType: string,
  objectId: string,
  userId: string,
  permission: "read" | "write" | "admin"
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/${objectType}s/${objectId}/permissions/share`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, permission }),
  });
}

export async function removeShare(
  workspaceId: string,
  objectType: string,
  objectId: string,
  userId: string
): Promise<void> {
  await apiFetch(
    `/api/v1/workspaces/${workspaceId}/${objectType}s/${objectId}/permissions/share/${userId}`,
    { method: "DELETE" }
  );
}

// --- Files ---

export async function uploadFile(
  workspaceId: string,
  file: File
): Promise<FileInfo> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);
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

export async function deleteFile(workspaceId: string, fileId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}`, { method: "DELETE" });
}

// --- Cross-notebook page index ---

export interface WorkspacePageEntry {
  id: string;
  name: string;
  notebook_id: string;
  notebook_name: string;
  folder_id: string | null;
  folder_name: string | null;
  updated_at: string;
}

export async function listWorkspacePages(
  workspaceId: string | null
): Promise<WorkspacePageEntry[]> {
  const data = await apiFetch<{ pages: WorkspacePageEntry[] }>(
    `${scope(workspaceId)}/pages`
  );
  return data.pages;
}


// --- Wiki: Backlinks, Outlinks, Page Graph, Semantic Search ---

export async function getBacklinks(
  workspaceId: string | null,
  notebookId: string,
  pageId: string
): Promise<PageLink[]> {
  const data = await apiFetch<{ backlinks: PageLink[] }>(
    `${scope(workspaceId)}/notebooks/${notebookId}/pages/${pageId}/backlinks`
  );
  return data.backlinks;
}

export async function getOutlinks(
  workspaceId: string | null,
  notebookId: string,
  pageId: string
): Promise<PageLink[]> {
  const data = await apiFetch<{ outlinks: PageLink[] }>(
    `${scope(workspaceId)}/notebooks/${notebookId}/pages/${pageId}/outlinks`
  );
  return data.outlinks;
}

export async function getPageGraph(
  workspaceId: string | null,
  notebookId: string
): Promise<PageGraph> {
  return apiFetch<PageGraph>(`${scope(workspaceId)}/notebooks/${notebookId}/graph`);
}

export async function semanticSearchPages(
  workspaceId: string | null,
  notebookId: string,
  query: string,
  limit = 20
): Promise<NotebookPage[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const data = await apiFetch<{ pages: NotebookPage[] }>(
    `${scope(workspaceId)}/notebooks/${notebookId}/pages/semantic-search?${params}`
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
    `/api/v1/workspaces/${workspaceId}/memory/agent-names`
  );
  return data.agent_names;
}
