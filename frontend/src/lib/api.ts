import {
  CommentThread,
  FileInfo,
  Folder,
  Page,
  TrashKind,
  TrashListing,
  WorkspaceTree,
  RegisterResponse,
  User,
  UserSearchResult,
  Table,
  TableRow,
  TableWithWorkspace,
  Workspace,
  ActivityTimeline,
  KnowledgeDensity,
  EmbeddingProjection,
} from "./types";

const TOKEN_KEY = "stash_token";
export const API_BASE = "";
const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

// Local trampoline so api.ts can fire analytics without importing analytics.ts
// (which would create a cycle — analytics.ts reads the auth token).
function trackEvent(
  event: string,
  properties?: Record<string, unknown>,
  opts?: { dedupeKey?: string; dedupeMs?: number },
): void {
  if (typeof window === "undefined") return;
  void import("./analytics").then((m) => m.track(event, properties, opts));
}
const DEFAULT_LOCAL_COLLAB_URL = "ws://localhost:3458";

// --- Token management (for CLI API key fallback) ---

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  if (AUTH0_ENABLED) return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  if (AUTH0_ENABLED) return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

export async function getAuth0AccessToken(): Promise<string | null> {
  if (!AUTH0_ENABLED || typeof window === "undefined") return null;
  const res = await fetch("/auth/access-token", { credentials: "include" });
  if (!res.ok) return null;
  const body = await res.json().catch(() => ({}));
  return typeof body.token === "string" && body.token ? body.token : null;
}

export async function getAuthToken(): Promise<string | null> {
  return getToken() ?? (await getAuth0AccessToken());
}

export function getCollabUrl(): string {
  const configured = process.env.NEXT_PUBLIC_COLLAB_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window === "undefined") return DEFAULT_LOCAL_COLLAB_URL;
  if (["localhost", "127.0.0.1"].includes(window.location.hostname)) {
    return DEFAULT_LOCAL_COLLAB_URL;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/collab`;
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
  const token = await getAuthToken();
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
  const token = await getAuthToken();
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
  role?: string;
  referral_source?: string;
  use_case?: string;
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

export interface WorkspaceSource {
  source: string; // native handle ("files"/"sessions") or connected-source id
  type: string; // 'native_files' | 'native_sessions' | 'github_repo' | ...
  capability: string; // 'navigable' | 'searchable' | 'queryable'
  display_name: string;
  // Present for connected sources (the integration page uses these).
  external_ref?: string | null;
  sync_status?: string | null; // 'idle' | 'syncing' | 'failed'
  sync_error?: string | null;
  last_synced_at?: string | null;
}

export interface SourceStatus extends WorkspaceSource {
  item_count: number | null; // null for queryable sources (no document table)
}

export interface SourceEntry {
  path?: string;
  id?: string;
  name: string;
  kind: string;
}

const NATIVE_SOURCE_TYPES = new Set(["native_files", "native_sessions"]);

export async function listWorkspaceSources(
  workspaceId: string,
): Promise<WorkspaceSource[]> {
  const data = await apiFetch<{ sources: WorkspaceSource[] }>(
    `/api/v1/workspaces/${workspaceId}/sources`,
  );
  // The sidebar's Sources section shows only connected sources; the native
  // file system and session transcripts already have their own sections.
  return data.sources.filter((s) => !NATIVE_SOURCE_TYPES.has(s.type));
}

export async function addWorkspaceSource(
  workspaceId: string,
  body: {
    source_type: string;
    external_ref?: string;
    display_name?: string;
    settings?: Record<string, unknown>;
  },
): Promise<{ id: string }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/sources`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function syncWorkspaceSource(
  workspaceId: string,
  sourceId: string,
): Promise<{ task_id: string }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/sources/${sourceId}/sync`, {
    method: "POST",
  });
}

export async function deleteWorkspaceSource(
  workspaceId: string,
  sourceId: string,
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/sources/${sourceId}`, {
    method: "DELETE",
  });
}

// --- per-integration page: status + content browsing ---

export async function getSourceStatus(
  workspaceId: string,
  sourceId: string,
): Promise<SourceStatus> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/sources/${sourceId}/status`);
}

export async function getSourceEntries(
  workspaceId: string,
  source: string,
  path = "",
): Promise<SourceEntry[]> {
  const q = path ? `?path=${encodeURIComponent(path)}` : "";
  const data = await apiFetch<{ entries: SourceEntry[] }>(
    `/api/v1/workspaces/${workspaceId}/sources/${source}/entries${q}`,
  );
  return data.entries;
}

export async function readSourceDoc(
  workspaceId: string,
  source: string,
  ref: string,
): Promise<{ name?: string; content?: string; url?: string | null }> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/sources/${source}/doc?ref=${encodeURIComponent(ref)}`,
  );
}

export interface SourceSearchHit {
  source: string;
  source_name?: string;
  ref: string;
  name?: string;
  snippet?: string;
}

export async function searchSource(
  workspaceId: string,
  query: string,
  source?: string,
): Promise<SourceSearchHit[]> {
  const params = new URLSearchParams({ q: query });
  if (source) params.set("source", source);
  const data = await apiFetch<{ results: SourceSearchHit[] }>(
    `/api/v1/workspaces/${workspaceId}/sources/search?${params.toString()}`,
  );
  return data.results;
}

export async function querySource(
  workspaceId: string,
  source: string,
  sql: string,
): Promise<{ columns?: string[]; rows?: unknown[][]; error?: string }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/sources/${source}/query`, {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

export async function fetchSourceHistory(
  workspaceId: string,
  source: string,
  since: string,
  until?: string,
): Promise<{ fetched: number; since: string; until: string | null }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/sources/${source}/history`, {
    method: "POST",
    body: JSON.stringify({ since, until }),
  });
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

// --- Discover (public catalog, no auth required) ---

export interface PublicCartridgeCard {
  id: string;
  slug: string;
  title: string;
  description: string;
  access: CartridgeVisibility;
  workspace_permission: CartridgeGeneralPermission;
  public_permission: CartridgeGeneralPermission;
  discoverable: boolean;
  cover_image_url: string | null;
  view_count: number;
  owner_name: string;
  owner_display_name: string;
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
  const page = await apiFetch<Page>(`/api/v1/workspaces/${workspaceId}/pages/new`, {
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
  trackEvent("web.page_created", { workspace_id: workspaceId });
  return page;
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
    collab_projection?: boolean;
    content_type?: "markdown" | "html";
    content_html?: string;
    html_layout?: "responsive" | "fixed-aspect";
    move_to_root?: boolean;
  }
): Promise<Page> {
  const result = await apiFetch<Page>(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}`,
    { method: "PATCH", body: JSON.stringify(data) },
  );
  // Only count actual content/title changes as "edits." Folder moves,
  // collab_projection passes, and pure layout flips are uninteresting.
  const isContentEdit =
    data.content !== undefined ||
    data.content_html !== undefined ||
    data.name !== undefined;
  if (isContentEdit) {
    trackEvent(
      "web.page_edited",
      { workspace_id: workspaceId, page_id: pageId },
      { dedupeKey: `${workspaceId}:${pageId}`, dedupeMs: 5 * 60 * 1000 },
    );
  }
  return result;
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

export async function deleteCommentThread(
  workspaceId: string,
  pageId: string,
  threadId: string,
): Promise<void> {
  await apiFetch(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}/comments/threads/${threadId}`,
    { method: "DELETE" },
  );
}

export async function deleteCommentMessage(
  workspaceId: string,
  pageId: string,
  messageId: string,
): Promise<{ thread: CommentThread | null; thread_deleted: boolean }> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/pages/${pageId}/comments/messages/${messageId}`,
    { method: "DELETE" },
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
  content_type: "markdown" | "html";
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
  days = 30,
  bucket = "day",
  workspaceId?: string | null,
  stashId?: string | null,
): Promise<ActivityTimeline> {
  const ws = workspaceId ? `&workspace_id=${workspaceId}` : "";
  const st = stashId ? `&stash_id=${stashId}` : "";
  return apiFetch(`/api/v1/me/activity-timeline?days=${days}&bucket=${bucket}${ws}${st}`);
}

export async function getKnowledgeDensity(
  maxClusters = 20, workspaceId?: string | null
): Promise<KnowledgeDensity> {
  const ws = workspaceId ? `&workspace_id=${workspaceId}` : "";
  return apiFetch(`/api/v1/me/knowledge-density?max_clusters=${maxClusters}${ws}`);
}

export async function getEmbeddingProjection(
  maxPoints = 500,
  source?: string,
  workspaceId?: string | null,
  stashId?: string | null,
): Promise<EmbeddingProjection> {
  const src = source ? `&source=${source}` : "";
  const ws = workspaceId ? `&workspace_id=${workspaceId}` : "";
  const st = stashId ? `&stash_id=${stashId}` : "";
  return apiFetch(`/api/v1/me/embedding-projection?max_points=${maxPoints}${src}${ws}${st}`);
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
  data: { name?: string; description?: string; folder_id?: string | null; move_to_root?: boolean }
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

export function workspaceFileDownloadUrl(workspaceId: string, fileId: string): string {
  return `/api/v1/workspaces/${workspaceId}/files/${fileId}/download`;
}

// Raw response shape from POST /workspaces/<id>/files. Polymorphic: the
// server routes .md/.html to the pages table (editable, commentable) and
// everything else to the files table (S3 blob). Discriminated by `kind`.
type UploadApiResponse = {
  kind: "file" | "page";
  id: string;
  workspace_id: string;
  folder_id: string | null;
  name: string;
  content_type: string;
  app_url: string;
  created_at: string;
  size_bytes?: number;
  url?: string;
  uploaded_by?: string;
  linked_table_id?: string | null;
  content_markdown?: string;
  content_html?: string;
  created_by?: string;
};

async function uploadAny(
  workspaceId: string,
  file: File,
  folderId?: string | null
): Promise<UploadApiResponse> {
  const token = await getAuthToken();
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
  const result = (await resp.json()) as UploadApiResponse;
  trackEvent("web.file_uploaded", {
    workspace_id: workspaceId,
    mime_type: file.type || "unknown",
    size_bucket: bucketSize(file.size),
    upload_kind: result.kind,
  });
  return result;
}

// Binary-only upload (icons, covers, editor images). Callers that
// already know the file is a blob and want a FileInfo back — asserts the
// server didn't route it to the pages table.
export async function uploadFile(
  workspaceId: string,
  file: File,
  folderId?: string | null
): Promise<FileInfo> {
  const result = await uploadAny(workspaceId, file, folderId);
  if (result.kind === "page") {
    throw new Error(
      `uploadFile got a page back from the server (${file.name}); ` +
        `use uploadFileOrPage for content that may be markdown or HTML.`
    );
  }
  return {
    id: result.id,
    workspace_id: result.workspace_id,
    folder_id: result.folder_id,
    name: result.name,
    content_type: result.content_type,
    size_bytes: result.size_bytes ?? 0,
    url: result.url ?? "",
    app_url: result.app_url,
    uploaded_by: result.uploaded_by ?? "",
    created_at: result.created_at,
    linked_table_id: result.linked_table_id ?? null,
  };
}

// Coarse size buckets keep the property cardinality small while still
// letting "uploads under 1MB vs 100MB+" comparisons happen.
function bucketSize(bytes: number): string {
  if (bytes < 100 * 1024) return "lt_100kb";
  if (bytes < 1024 * 1024) return "lt_1mb";
  if (bytes < 10 * 1024 * 1024) return "lt_10mb";
  if (bytes < 100 * 1024 * 1024) return "lt_100mb";
  return "gte_100mb";
}

// Polymorphic upload: the server creates a page row for .md/.html and a
// file row for everything else. Use this for drag-drop and Quick Add
// flows where the user might be giving us either content or a binary.
export type UploadResult =
  | { kind: "file"; file: FileInfo }
  | { kind: "page"; page: Page };

export async function uploadFileOrPage(
  workspaceId: string,
  file: File,
  folderId?: string | null
): Promise<UploadResult> {
  const result = await uploadAny(workspaceId, file, folderId);
  if (result.kind === "page") {
    const page: Page = {
      id: result.id,
      workspace_id: result.workspace_id,
      folder_id: result.folder_id,
      name: result.name,
      content_type: result.content_type === "html" ? "html" : "markdown",
      content_markdown: result.content_markdown ?? "",
      content_html: result.content_html ?? "",
      html_layout: "responsive",
      created_by: result.created_by ?? "",
      updated_by: null,
      created_at: result.created_at,
      updated_at: result.created_at,
    };
    return { kind: "page", page };
  }
  const f: FileInfo = {
    id: result.id,
    workspace_id: result.workspace_id,
    folder_id: result.folder_id,
    name: result.name,
    content_type: result.content_type,
    size_bytes: result.size_bytes ?? 0,
    url: result.url ?? "",
    app_url: result.app_url,
    uploaded_by: result.uploaded_by ?? "",
    created_at: result.created_at,
    linked_table_id: result.linked_table_id ?? null,
  };
  return { kind: "file", file: f };
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

export async function ingestXlsxFile(
  workspaceId: string,
  fileId: string,
): Promise<{ tables: Table[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}/ingest-xlsx`, {
    method: "POST",
  });
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
  // DB row id (sessions.id). Null when history exists with no sessions row;
  // delete is keyed by this id.
  id: string | null;
  title: string;
  linear_tickets: LinearTicketLabel[];
  workspace_id: string | null;
  workspace_name: string | null;
  user_name: string;
  agent_name: string | null;
  event_count: number;
  started_at: string;
  last_event_at: string;
  session_folder_id: string | null;
  session_folder_name: string | null;
}

export type GeneralPermission = "none" | "read" | "write";
// Stored visibility is two-state (the "workspace" tier was dropped after the
// 1:1 workspace↔user migration). "shared" is a derived display state.
export type SessionFolderVisibility = "private" | "public";
export type DisplayVisibility = "private" | "shared" | "public";

// The label to show: public link, else "shared" if anyone's been invited, else
// private. Folders and cartridges both feed (access, count) in.
export function displayVisibility(
  access: "private" | "public",
  shareCount: number,
): DisplayVisibility {
  if (access === "public") return "public";
  return shareCount > 0 ? "shared" : "private";
}

export interface SessionFolder {
  id: string;
  workspace_id: string;
  slug: string;
  name: string;
  owner_display_name: string | null;
  access: SessionFolderVisibility;
  workspace_permission: GeneralPermission;
  public_permission: GeneralPermission;
  discoverable: boolean;
  is_default: boolean;
  view_count: number;
  session_count: number;
  share_count: number;
}

export async function listSessionFolders(workspaceId: string): Promise<SessionFolder[]> {
  const data = await apiFetch<{ folders: SessionFolder[] }>(
    `/api/v1/workspaces/${workspaceId}/session-folders`,
  );
  return data.folders;
}

export async function createSessionFolder(
  workspaceId: string,
  name: string,
): Promise<SessionFolder> {
  return apiFetch<SessionFolder>(`/api/v1/workspaces/${workspaceId}/session-folders`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function updateSessionFolder(
  workspaceId: string,
  folderId: string,
  data: {
    name?: string;
    workspace_permission?: GeneralPermission;
    public_permission?: GeneralPermission;
    discoverable?: boolean;
  },
): Promise<SessionFolder> {
  return apiFetch<SessionFolder>(
    `/api/v1/workspaces/${workspaceId}/session-folders/${folderId}`,
    { method: "PATCH", body: JSON.stringify(data) },
  );
}

export async function deleteSessionFolder(workspaceId: string, folderId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/session-folders/${folderId}`, {
    method: "DELETE",
  });
}

// Move one or more sessions into a folder (or out, with folderId null).
export async function assignSessionFolder(
  workspaceId: string,
  sessionRowIds: string[],
  folderId: string | null,
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/session-folders/assign`, {
    method: "POST",
    body: JSON.stringify({ session_row_ids: sessionRowIds, folder_id: folderId }),
  });
}

export interface PublicSessionFolder {
  folder: SessionFolder;
  sessions: {
    id: string;
    session_id: string;
    agent_name: string;
    cwd: string | null;
    user_name: string | null;
    event_count: number;
    started_at: string | null;
    last_event_at: string | null;
  }[];
}

export async function getPublicSessionFolder(slug: string): Promise<PublicSessionFolder> {
  return apiFetch<PublicSessionFolder>(`/api/v1/session-folders/${slug}`);
}

export interface LinearTicketLabel {
  ticket_identifier: string;
  ticket_title: string | null;
  ticket_url: string | null;
  source: string;
  confidence: number;
  linear_issue_id: string | null;
  ticket_status: string | null;
  ticket_assignee_name: string | null;
  ticket_team_key: string | null;
  ticket_team_name: string | null;
  ticket_project_name: string | null;
  linear_updated_at: string | null;
  enriched_at: string | null;
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
  title: string;
  agent_name: string;
  cwd: string | null;
  files_touched: string[] | string;
  linear_tickets: LinearTicketLabel[];
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

export async function renameSession(
  workspaceId: string,
  sessionId: string,
  title: string
): Promise<{ title: string }> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/sessions/${encodeURIComponent(sessionId)}/title`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }
  );
}

export async function deleteSession(
  workspaceId: string,
  sessionRowId: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/sessions/${sessionRowId}`, {
    method: "DELETE",
  });
}

export async function materializeSession(
  workspaceId: string,
  sessionId: string
): Promise<MaterializedSession> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/materialize`, {
    method: "POST",
  });
}

// --- Pins + recents (per user, per workspace) ---

export type PinKind = "cartridges" | "sessions" | "files";

export interface WorkspacePins {
  cartridges: string[];
  sessions: string[];
  files: string[];
}

export interface RecentEntry {
  object_id: string;
  kind: string;
}

export async function getWorkspacePins(workspaceId: string): Promise<WorkspacePins> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/pins`);
}

export async function setWorkspacePins(
  workspaceId: string,
  kind: PinKind,
  ids: string[]
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/pins/${kind}`, {
    method: "PUT",
    body: JSON.stringify({ ids }),
  });
}

export async function getWorkspaceRecents(workspaceId: string): Promise<RecentEntry[]> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/recents`);
}

export async function recordWorkspaceRecent(
  workspaceId: string,
  objectId: string,
  kind: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/recents`, {
    method: "POST",
    body: JSON.stringify({ object_id: objectId, kind }),
  });
}

// --- Cartridges (publishable bundles of pages, sessions, and files) ---

export type CollectableObjectType = "folder" | "page" | "table" | "file" | "session";

export interface CartridgeItemSpec {
  object_type: CollectableObjectType;
  object_id: string;
  position?: number;
  label_override?: string | null;
}

export type CartridgeVisibility = "private" | "public";
export type CartridgeGeneralPermission = "none" | "read" | "write";

export interface CreatedCartridge {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string;
  owner_id: string;
  owner_name: string;
  owner_display_name: string | null;
  access: CartridgeVisibility;
  workspace_permission: CartridgeGeneralPermission;
  public_permission: CartridgeGeneralPermission;
  discoverable: boolean;
  cover_image_url: string | null;
  icon_url: string | null;
  view_count: number;
  share_count: number;
  items: CartridgeItemSpec[];
  is_external: boolean;
  added_to_workspace_id: string | null;
  forked_from_cartridge_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublishedCartridgeResult {
  cartridge: CreatedCartridge;
  url: string;
  cartridge_id: string;
  cartridge_slug: string;
}

export async function createCartridge(
  workspaceId: string,
  title: string,
  items: CartridgeItemSpec[],
  opts: {
    description?: string;
    workspace_permission?: CartridgeGeneralPermission;
    public_permission?: CartridgeGeneralPermission;
    discoverable?: boolean;
  } = {}
): Promise<CreatedCartridge> {
  const cartridge = await apiFetch<CreatedCartridge>(
    `/api/v1/workspaces/${workspaceId}/cartridges`,
    {
      method: "POST",
      body: JSON.stringify({
        title,
        description: opts.description ?? "",
        workspace_permission: opts.workspace_permission ?? "read",
        public_permission: opts.public_permission ?? "none",
        discoverable: opts.discoverable ?? false,
        cover_image_url: null,
        items: items.map((it, i) => ({
          object_type: it.object_type,
          object_id: it.object_id,
          position: it.position ?? i,
          label_override: it.label_override ?? null,
        })),
      }),
    },
  );
  trackEvent("web.stash_created", {
    workspace_id: workspaceId,
    item_count: items.length,
    public: (opts.public_permission ?? "none") !== "none",
    kind: "manual",
  });
  return cartridge;
}

export async function publishCartridge(
  workspaceId: string,
  title: string,
  items: CartridgeItemSpec[],
  opts: {
    description?: string;
    workspace_permission?: CartridgeGeneralPermission;
    public_permission?: Exclude<CartridgeGeneralPermission, "none">;
    discoverable?: boolean;
  } = {}
): Promise<PublishedCartridgeResult> {
  const result = await apiFetch<PublishedCartridgeResult>(
    `/api/v1/workspaces/${workspaceId}/cartridges/publish`,
    {
      method: "POST",
      body: JSON.stringify({
        title,
        description: opts.description ?? "",
        workspace_permission: opts.workspace_permission ?? "read",
        public_permission: opts.public_permission ?? "read",
        discoverable: opts.discoverable ?? false,
        cover_image_url: null,
        items: items.map((it, i) => ({
          object_type: it.object_type,
          object_id: it.object_id,
          position: it.position ?? i,
          label_override: it.label_override ?? null,
        })),
      }),
    },
  );
  trackEvent("web.stash_created", {
    workspace_id: workspaceId,
    item_count: items.length,
    public: true,
    discoverable: opts.discoverable ?? false,
    kind: "publish",
  });
  return result;
}

export interface WorkspaceCartridge {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string;
  owner_id: string;
  owner_name: string;
  owner_display_name: string | null;
  access: CartridgeVisibility;
  workspace_permission: CartridgeGeneralPermission;
  public_permission: CartridgeGeneralPermission;
  discoverable: boolean;
  cover_image_url: string | null;
  icon_url: string | null;
  view_count: number;
  share_count: number;
  items: CartridgeItemSpec[];
  is_external: boolean;
  added_to_workspace_id: string | null;
  forked_from_cartridge_id: string | null;
  created_at: string;
  updated_at: string;
}

export type CartridgeMemberPermission = "read" | "write" | "admin";

export interface CartridgeMember {
  user_id: string;
  name: string;
  display_name: string;
  permission: CartridgeMemberPermission;
  granted_by: string | null;
  created_at: string;
}

export interface PublicCartridgeItem {
  object_type: CollectableObjectType;
  object_id: string;
  position: number;
  label: string;
  inline: Record<string, unknown>;
}

export interface PublicCartridgeDetail {
  cartridge: WorkspaceCartridge;
  workspace_name: string;
  items: PublicCartridgeItem[];
  can_write: boolean;
}

export async function listStashes(workspaceId: string): Promise<WorkspaceCartridge[]> {
  const data = await apiFetch<{ cartridges: WorkspaceCartridge[] }>(
    `/api/v1/workspaces/${workspaceId}/cartridges`
  );
  return data.cartridges;
}

export async function listObjectStashes(
  workspaceId: string,
  objectType: CollectableObjectType,
  objectId: string
): Promise<WorkspaceCartridge[]> {
  const data = await apiFetch<{ cartridges: WorkspaceCartridge[] }>(
    `/api/v1/workspaces/${workspaceId}/cartridges/objects/${objectType}/${objectId}`
  );
  return data.cartridges;
}

export async function deleteCartridge(stashId: string): Promise<void> {
  await apiFetch(`/api/v1/cartridges/${stashId}`, { method: "DELETE" });
}

export async function updateCartridge(
  stashId: string,
  data: {
    title?: string;
    description?: string;
    workspace_permission?: CartridgeGeneralPermission;
    public_permission?: CartridgeGeneralPermission;
    discoverable?: boolean;
    cover_image_url?: string | null;
    icon_url?: string | null;
    items?: CartridgeItemSpec[];
  }
): Promise<WorkspaceCartridge> {
  return apiFetch(`/api/v1/cartridges/${stashId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function listCartridgeMembers(stashId: string): Promise<CartridgeMember[]> {
  const data = await apiFetch<{ members: CartridgeMember[] }>(
    `/api/v1/cartridges/${stashId}/members`
  );
  return data.members;
}

export async function addCartridgeMember(
  stashId: string,
  userId: string,
  permission: CartridgeMemberPermission
): Promise<CartridgeMember> {
  return apiFetch(`/api/v1/cartridges/${stashId}/members`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, permission }),
  });
}

export async function removeCartridgeMember(stashId: string, userId: string): Promise<void> {
  await apiFetch(`/api/v1/cartridges/${stashId}/members/${userId}`, { method: "DELETE" });
}

export async function getPublicCartridge(slug: string): Promise<PublicCartridgeDetail> {
  return apiFetch(`/api/v1/cartridges/${slug}`);
}

export async function createSharedCartridgePage(
  stashId: string,
  data: {
    name: string;
    content: string;
    content_type?: "markdown" | "html";
    content_html?: string;
    html_layout?: "responsive" | "fixed-aspect";
  }
): Promise<Page> {
  return apiFetch(`/api/v1/cartridges/${stashId}/shared-pages`, {
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

export async function addExternalCartridge(
  slug: string,
  workspaceId: string
): Promise<WorkspaceCartridge> {
  return apiFetch(`/api/v1/cartridges/${slug}/add-to-workspace`, {
    method: "POST",
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
}

export async function removeExternalCartridge(
  workspaceId: string,
  stashId: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/external-cartridges/${stashId}`, {
    method: "DELETE",
  });
}

// --- Stash invites ---

export interface CartridgeInvite {
  id: string;
  cartridge_id: string;
  cartridge_slug: string;
  cartridge_title: string;
  cartridge_description: string;
  source_workspace_id: string;
  source_workspace_name: string;
  invited_by_user_id: string;
  invited_by_name: string;
  invited_by_display_name: string;
  permission: CartridgeMemberPermission;
  created_at: string;
}

export async function listCartridgeInvites(): Promise<CartridgeInvite[]> {
  const data = await apiFetch<{ invites: CartridgeInvite[] }>("/api/v1/cartridge-invites");
  return data.invites;
}

export async function dismissCartridgeInvite(inviteId: string): Promise<void> {
  await apiFetch(`/api/v1/cartridge-invites/${inviteId}/dismiss`, { method: "POST" });
}

// --- Workspace-wide page index ---

export interface WorkspacePageEntry {
  id: string;
  name: string;
  content_type: "markdown" | "html";
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
  actor: { name: string; display_name: string };
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
  const token = await getAuthToken();
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

// --- Workspace overview, sessions, files, and cartridges ---

export interface WorkspaceSidebarSession {
  id: string | null;
  session_id: string;
  title: string;
  linear_tickets: LinearTicketLabel[];
  user_name: string;
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
  content_type: "markdown" | "html";
  folder_id: string | null;
}
export interface WorkspaceFile {
  id: string;
  name: string;
  folder_id: string | null;
  size_bytes: number;
  content_type: string;
  url: string | null;
  app_url?: string;
  created_at: string;
  linked_table_id?: string | null;
}
export interface WorkspaceFiles {
  folders: WorkspaceFolder[];
  pages: WorkspacePage[];
  files: WorkspaceFile[];
}

export interface WorkspaceSidebarCartridge {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string;
  access: CartridgeVisibility;
  workspace_permission: CartridgeGeneralPermission;
  public_permission: CartridgeGeneralPermission;
  discoverable: boolean;
  is_external: boolean;
  forked_from_cartridge_id: string | null;
  item_count: number;
  items?: CartridgeItemSpec[];
  updated_at: string;
}

export interface WorkspaceOverview {
  sessions: WorkspaceSidebarSession[];
  files: WorkspaceFiles;
  cartridges?: WorkspaceSidebarCartridge[];
}

export async function getWorkspaceOverview(workspaceId: string): Promise<WorkspaceOverview> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/overview`);
}

export interface WorkspaceSidebar {
  sessions: WorkspaceSidebarSession[];
  files: WorkspaceFiles;
  cartridges?: WorkspaceSidebarCartridge[];
}

// In-memory store for the last ETag seen per workspace, so navigating between
// workspaces hits the cached payload instead of refetching.
const _sidebarEtags: Record<string, string> = {};
const _sidebarCache: Record<string, WorkspaceSidebar> = {};

export async function getWorkspaceSidebar(workspaceId: string): Promise<WorkspaceSidebar> {
  const token = await getAuthToken();
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
  pages: { id: string; name: string; content_type: "markdown" | "html" }[];
  files: Omit<WorkspaceFile, "folder_id">[];
  tables: { id: string; name: string; row_count: number }[];
}

export async function getFolderContents(
  workspaceId: string,
  folderId: string
): Promise<FolderContents> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/folders/${folderId}/contents`
  );
}

// --- Shared with me ---

export type SharedObjectType = "folder" | "session_folder" | "page" | "file" | "table" | "session";

export interface SharedWithMeItem {
  object_type: SharedObjectType;
  object_id: string;
  name: string;
  workspace_id: string;
  workspace_name: string;
  shared_by: string | null;
  permission: "read" | "write";
}

export async function listSharedWithMe(): Promise<SharedWithMeItem[]> {
  const res = await apiFetch<{ items: SharedWithMeItem[] }>("/api/v1/share/with-me");
  return res.items;
}

// Sessions inside a folder shared with you, in SessionSummary shape so the
// shared view renders the same chronological/filter browser as your own.
export async function listSharedSessionFolderSessions(
  folderId: string,
): Promise<SessionSummary[]> {
  const res = await apiFetch<{ sessions: SessionSummary[] }>(
    `/api/v1/share/session-folders/${folderId}/sessions`
  );
  return res.sessions;
}

export interface ObjectShare {
  principal_type: string;
  principal_id: string | null;
  label: string;
  email: string | null;
  permission: GeneralPermission;
  pending: boolean;
}

export async function listObjectShares(
  objectType: SharedObjectType,
  objectId: string,
): Promise<ObjectShare[]> {
  const res = await apiFetch<{ shares: ObjectShare[] }>(
    `/api/v1/share?object_type=${objectType}&object_id=${objectId}`,
  );
  return res.shares;
}

export async function shareObjectByEmail(
  objectType: SharedObjectType,
  objectId: string,
  email: string,
  permission: GeneralPermission = "read",
): Promise<void> {
  await apiFetch("/api/v1/share", {
    method: "POST",
    body: JSON.stringify({ object_type: objectType, object_id: objectId, email, permission }),
  });
}

export async function unshareObject(
  objectType: SharedObjectType,
  objectId: string,
  principalType: string,
  principalId: string,
): Promise<void> {
  await apiFetch("/api/v1/share", {
    method: "DELETE",
    body: JSON.stringify({
      object_type: objectType,
      object_id: objectId,
      principal_type: principalType,
      principal_id: principalId,
    }),
  });
}

// --- Trash ---

// All three flavors share the same URL shape (`/{kind}s/{id}`), so a single
// helper covers trash/restore/purge instead of three near-identical pairs.
const TRASH_KIND_PATH: Record<TrashKind, string> = {
  page: "pages",
  file: "files",
  session: "sessions",
};

export async function trashItem(
  workspaceId: string,
  kind: TrashKind,
  id: string,
): Promise<void> {
  await apiFetch(
    `/api/v1/workspaces/${workspaceId}/${TRASH_KIND_PATH[kind]}/${id}`,
    { method: "DELETE" },
  );
}

export async function restoreItem(
  workspaceId: string,
  kind: TrashKind,
  id: string,
): Promise<void> {
  await apiFetch(
    `/api/v1/workspaces/${workspaceId}/${TRASH_KIND_PATH[kind]}/${id}/restore`,
    { method: "POST" },
  );
}

export async function purgeItem(
  workspaceId: string,
  kind: TrashKind,
  id: string,
): Promise<void> {
  await apiFetch(
    `/api/v1/workspaces/${workspaceId}/${TRASH_KIND_PATH[kind]}/${id}/purge`,
    { method: "DELETE" },
  );
}

export async function getTrash(workspaceId: string): Promise<TrashListing> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/trash`);
}
