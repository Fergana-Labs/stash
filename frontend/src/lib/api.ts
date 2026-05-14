import {
  Attachment,
  FileInfo,
  HistoryEvent,
  HistoryEventWithContext,
  History,
  HistoryWithWorkspace,
  JoinRequest,
  Folder,
  Page,
  PageGraph,
  PageLink,
  WorkspaceTree,
  ObjectPermission,
  RegisterResponse,
  User,
  UserSearchResult,
  Table,
  TableRow,
  TableWithWorkspace,
  Workspace,
  WorkspaceMember,
  WorkspacePublicInfo,
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
    is_public?: boolean;
    discoverable?: boolean;
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

export async function forkWorkspace(
  workspaceId: string,
  name?: string
): Promise<Workspace> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/fork`, {
    method: "POST",
    body: JSON.stringify(name ? { name } : {}),
  });
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

// --- Join Requests ---

export async function getWorkspacePublicInfo(workspaceId: string): Promise<WorkspacePublicInfo> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/public-info`);
}

export async function createJoinRequest(workspaceId: string): Promise<JoinRequest> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/join-requests`, { method: "POST" });
}

export async function listJoinRequests(workspaceId: string): Promise<{ requests: JoinRequest[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/join-requests`);
}

export async function approveJoinRequest(workspaceId: string, requestId: string): Promise<JoinRequest> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/join-requests/${requestId}/approve`, { method: "POST" });
}

export async function denyJoinRequest(workspaceId: string, requestId: string): Promise<JoinRequest> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/join-requests/${requestId}/deny`, { method: "POST" });
}

export async function getMyJoinRequest(workspaceId: string): Promise<JoinRequest> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/join-requests/mine`);
}

// --- Discover (public catalog, no auth required) ---

export interface CatalogCard {
  id: string;
  name: string;
  summary: string | null;
  description: string;
  is_public: boolean;
  tags: string[];
  category: string | null;
  discoverable: boolean;
  featured: boolean;
  cover_image_url: string | null;
  creator_id: string;
  creator_name: string;
  creator_display_name: string | null;
  member_count: number;
  fork_count: number;
  page_count: number;
  table_count: number;
  file_count: number;
  history_event_count: number;
  forked_from_workspace_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublicWorkspaceDetail {
  workspace: CatalogCard;
  folders: {
    id: string;
    name: string;
    parent_folder_id: string | null;
    page_count: number;
    updated_at: string;
  }[];
  root_pages: { id: string; name: string; updated_at: string }[];
  tables: { id: string; name: string; row_count: number; updated_at: string }[];
  files: { id: string; name: string; size_bytes: number; created_at: string }[];
}

export async function fetchPublicWorkspace(
  workspaceId: string,
  origin?: string
): Promise<PublicWorkspaceDetail | null> {
  const base = origin ?? "";
  const res = await fetch(`${base}/api/v1/discover/workspaces/${workspaceId}`, {
    next: { revalidate: 60 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, `discover fetch failed: ${res.status}`);
  return res.json();
}

// --- Wiki: folders (nested) and pages ---

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

// Quick-add drops (notes, links, files) all funnel into a single "Hopper"
// folder at the wiki root. We auto-create it on first use so the user
// doesn't have to set anything up.
const HOPPER_FOLDER_NAME = "Hopper";
const hopperCache = new Map<string, string>();

export async function ensureHopperFolder(workspaceId: string): Promise<string> {
  const cached = hopperCache.get(workspaceId);
  if (cached) return cached;
  const { folders } = await listFolders(workspaceId);
  const existing = folders.find(
    (f) => !f.parent_folder_id && f.name === HOPPER_FOLDER_NAME
  );
  if (existing) {
    hopperCache.set(workspaceId, existing.id);
    return existing.id;
  }
  const created = await createFolder(workspaceId, HOPPER_FOLDER_NAME, null);
  hopperCache.set(workspaceId, created.id);
  return created.id;
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
  options?: { content_type?: "markdown" | "html"; content_html?: string }
): Promise<Page> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/pages/new`, {
    method: "POST",
    body: JSON.stringify({
      name,
      folder_id: folderId || null,
      content: content || "",
      content_type: options?.content_type ?? "markdown",
      content_html: options?.content_html ?? "",
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

// Cross-workspace flat page list, used by wiki-link autocomplete to resolve
// links to pages outside the active workspace.
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

export interface CreateHistoryEventInput {
  agent_name: string;
  event_type: string;
  content: string;
  session_id?: string | null;
  tool_name?: string | null;
  metadata?: Record<string, unknown>;
  attachments?: Attachment[] | null;
}

export async function createWorkspaceHistoryEvent(
  workspaceId: string,
  input: CreateHistoryEventInput
): Promise<HistoryEvent> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/memory/events`, {
    method: "POST",
    body: JSON.stringify(input),
  });
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

// --- Sessions (history events grouped by session_id) ---

export interface SessionSummary {
  session_id: string;
  workspace_id: string | null;
  workspace_name: string | null;
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

export async function materializeSession(
  workspaceId: string,
  sessionId: string
): Promise<MaterializedSession> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/materialize`, {
    method: "POST",
  });
}

// --- Views (curated bundles of items shareable as /v/{slug}) ---

export type CollectableObjectType = "folder" | "page" | "table" | "file" | "history";

export interface ViewItemSpec {
  object_type: CollectableObjectType;
  object_id: string;
  position?: number;
  label_override?: string | null;
}

export interface CreatedView {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string;
  owner_id: string;
  view_count: number;
  items: ViewItemSpec[];
  created_at: string;
  updated_at: string;
}

export interface SharedViewResult {
  view: CreatedView;
  url: string;
  view_id: string;
  view_slug: string;
}

export async function createView(
  workspaceId: string,
  title: string,
  items: ViewItemSpec[],
  opts: { description?: string; is_public?: boolean } = {}
): Promise<CreatedView> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/views`, {
    method: "POST",
    body: JSON.stringify({
      title,
      description: opts.description ?? "",
      is_public: opts.is_public ?? false,
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

export async function createSharedView(
  workspaceId: string,
  title: string,
  items: ViewItemSpec[],
  opts: { description?: string; ensure?: "link" | "public" } = {}
): Promise<SharedViewResult> {
  const ensure = opts.ensure ?? "link";
  return apiFetch(`/api/v1/workspaces/${workspaceId}/views/share-bundle?ensure=${ensure}`, {
    method: "POST",
    body: JSON.stringify({
      title,
      description: opts.description ?? "",
      is_public: ensure === "public",
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

export interface StashView {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string;
  owner_id: string;
  is_public: boolean;
  cover_image_url: string | null;
  view_count: number;
  items: ViewItemSpec[];
  created_at: string;
  updated_at: string;
}

export async function listViews(workspaceId: string): Promise<StashView[]> {
  const data = await apiFetch<{ views: StashView[] }>(
    `/api/v1/workspaces/${workspaceId}/views`
  );
  return data.views;
}

export async function deleteView(viewId: string): Promise<void> {
  await apiFetch(`/api/v1/views/${viewId}`, { method: "DELETE" });
}

// --- Workspace-wide page index (used by wiki-link autocomplete + click-resolve) ---

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


// --- Wiki: Backlinks, Outlinks, Page Graph, Semantic Search ---

export async function getBacklinks(
  workspaceId: string,
  pageId: string
): Promise<PageLink[]> {
  const data = await apiFetch<{ backlinks: PageLink[] }>(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}/backlinks`
  );
  return data.backlinks;
}

export async function getOutlinks(
  workspaceId: string,
  pageId: string
): Promise<PageLink[]> {
  const data = await apiFetch<{ outlinks: PageLink[] }>(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}/outlinks`
  );
  return data.outlinks;
}

export async function getWorkspaceGraph(
  workspaceId: string
): Promise<PageGraph> {
  return apiFetch<PageGraph>(`/api/v1/workspaces/${workspaceId}/graph`);
}

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

// --- Activity feed ---

export interface ActivityEvent {
  kind: string;
  ts: string;
  actor: { name: string; display_name: string | null };
  target_id: string;
  target_label: string;
  stash_id?: string;
  stash_name?: string;
}

export async function listActivity(limit = 100): Promise<ActivityEvent[]> {
  return apiFetch(`/api/v1/me/activity?limit=${limit}`);
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

export async function getStashTranscript(
  stashId: string,
  sessionId: string
): Promise<SessionTranscript> {
  return apiFetch(
    `/api/v1/workspaces/${stashId}/transcripts/${encodeURIComponent(sessionId)}`
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
  stashId: string,
  sessionId: string
): Promise<SessionEvent[]> {
  const res = await apiFetch<{ events: SessionEvent[] }>(
    `/api/v1/workspaces/${stashId}/transcripts/${encodeURIComponent(sessionId)}/events`
  );
  return res.events;
}

// --- Stashes (canonical naming, aliases /api/v1/workspaces/* on the server) ---

export interface StashSpineSession {
  session_id: string;
  title: string;
  agent_name: string;
  size_bytes: number;
  last_at: string;
  updated_at: string;
}

// Unified Wiki — one tree, no Drive/Skill split. Folders, pages, and files
// each carry their parent so the frontend can build the hierarchy.
export interface WikiFolder {
  id: string;
  name: string;
  parent_folder_id: string | null;
  page_count: number;
  file_count: number;
  has_skill: boolean;
}
export interface WikiPage {
  id: string;
  name: string;
  folder_id: string | null;
}
export interface WikiFile {
  id: string;
  name: string;
  folder_id: string | null;
  size_bytes: number;
  content_type: string;
  url: string | null;
  created_at: string;
  linked_table_id?: string | null;
}
export interface StashWiki {
  folders: WikiFolder[];
  pages: WikiPage[];
  files: WikiFile[];
}
export interface StashHandoffMetadata {
  present: boolean;
  generated_at: string | null;
  stale: boolean;
  pinned_at: string | null;
}
export interface StashOverview {
  handoff_metadata: StashHandoffMetadata;
  sessions: StashSpineSession[];
  wiki: StashWiki;
}

export async function getStashOverview(stashId: string): Promise<StashOverview> {
  return apiFetch(`/api/v1/stashes/${stashId}/overview`);
}

export interface StashSidebar {
  sessions: StashSpineSession[];
  wiki: StashWiki;
}

// In-memory store for the last ETag seen per stash, so navigating between
// stashes hits the cached payload instead of refetching.
const _sidebarEtags: Record<string, string> = {};
const _sidebarCache: Record<string, StashSidebar> = {};

export async function getStashSidebar(stashId: string): Promise<StashSidebar> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const cached = _sidebarEtags[stashId];
  if (cached) headers["If-None-Match"] = cached;

  const res = await fetch(`${API_BASE}/api/v1/stashes/${stashId}/sidebar`, {
    method: "GET",
    headers,
  });
  if (res.status === 304 && _sidebarCache[stashId]) return _sidebarCache[stashId];
  if (!res.ok) throw new ApiError(res.status, `sidebar fetch failed: ${res.status}`);
  const etag = res.headers.get("etag");
  if (etag) _sidebarEtags[stashId] = etag;
  const body = (await res.json()) as StashSidebar;
  _sidebarCache[stashId] = body;
  return body;
}

export type StashHandoffReason =
  | "fresh"
  | "pinned"
  | "stale"
  | "never_generated"
  | "failed";

export interface StashHandoff {
  present: boolean;
  reason: StashHandoffReason;
  body_markdown?: string;
  generated_at?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  turns_used?: number | null;
  tool_calls_used?: number | null;
  pinned_at: string | null;
  pinned_by?: string | null;
  last_error: string | null;
}

export async function getStashHandoff(stashId: string): Promise<StashHandoff> {
  return apiFetch(`/api/v1/stashes/${stashId}/handoff`);
}

export async function regenerateStashHandoff(stashId: string): Promise<StashHandoff> {
  return apiFetch(`/api/v1/stashes/${stashId}/handoff/regenerate`, { method: "POST" });
}

export async function editStashHandoff(
  stashId: string,
  bodyMarkdown: string,
): Promise<StashHandoff> {
  return apiFetch(`/api/v1/stashes/${stashId}/handoff`, {
    method: "PATCH",
    body: JSON.stringify({ body_markdown: bodyMarkdown }),
  });
}

export async function unpinStashHandoff(stashId: string): Promise<StashHandoff> {
  return apiFetch(`/api/v1/stashes/${stashId}/handoff/unpin`, { method: "POST" });
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
  files: Omit<WikiFile, "folder_id">[];
}

export async function getFolderContents(
  workspaceId: string,
  folderId: string
): Promise<FolderContents> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/folders/${folderId}/contents`
  );
}

// Legacy skill detail endpoint — kept for backward compat with anything
// still calling it (e.g. the soon-to-be-redirected /skills/[name] route).
export interface StashSkillDetail {
  folder_id: string;
  name: string;
  description: string;
  when_to_use: string;
  body: string;
  files: { id: string; name: string; updated_at: string; content: string }[];
  combined: string;
}

export async function getStashSkill(stashId: string, name: string): Promise<StashSkillDetail> {
  return apiFetch(`/api/v1/stashes/${stashId}/skills/${encodeURIComponent(name)}`);
}

