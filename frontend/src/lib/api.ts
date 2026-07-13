import {
  CommentThread,
  FileInfo,
  Folder,
  Page,
  TrashKind,
  TrashListing,
  Tree,
  RegisterResponse,
  User,
  UserSearchResult,
  Table,
  TableRow,
  TableWithOwner,
  ActivityTimeline,
  KnowledgeDensity,
  EmbeddingProjection,
  Workspace,
} from "./types";
import { getScopeUserId, SCOPE_HEADER } from "./scope-store";

const TOKEN_KEY = "stash_token";
export const API_BASE = "";
const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

// Local trampoline so api.ts can fire analytics without importing analytics.ts
// (which would create a cycle — analytics.ts imports getAuthToken from here).
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

// Legacy browser sign-ins stored a permanent mc_ API key in localStorage.
// Revoke it server-side before discarding so the credential dies with the
// session instead of staying valid forever.
export async function revokeStoredApiKey(): Promise<void> {
  if (typeof window === "undefined") return;
  const token = localStorage.getItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
  if (!token) return;
  await fetch(`${API_BASE}/api/v1/users/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => {});
}

// Cached briefly so chatty views don't pay a serial round-trip to the
// Next.js auth route before every backend call.
const AUTH0_TOKEN_CACHE_MS = 60_000;
let auth0TokenCache: { token: string; fetchedAt: number } | null = null;

export async function getAuth0AccessToken(): Promise<string | null> {
  if (!AUTH0_ENABLED || typeof window === "undefined") return null;
  if (auth0TokenCache && Date.now() - auth0TokenCache.fetchedAt < AUTH0_TOKEN_CACHE_MS) {
    return auth0TokenCache.token;
  }
  const res = await fetch("/auth/access-token", { credentials: "include" });
  if (!res.ok) return null;
  const body = await res.json().catch(() => ({}));
  if (typeof body.token !== "string" || !body.token) return null;
  auth0TokenCache = { token: body.token, fetchedAt: Date.now() };
  return body.token;
}

// The onboarding agent prompt needs a persistent API key — agents can't use
// the browser's short-lived Auth0 access token. Self-hosted browsers already
// hold their key; under managed Auth0 the browser never mints keys, so this
// returns null and the agent prompt tells the user to run `stash signin`.
export function getAgentApiKey(): string | null {
  return getToken();
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
  const scopeUserId = getScopeUserId();
  if (scopeUserId) headers[SCOPE_HEADER] = scopeUserId;
  return fetch(`${API_BASE}${path}`, { headers });
}

// The user is the scope. Every scoped collection and every object the user
// owns lives under this base; shared/by-id reads use the canonical
// /api/v1/{pages,files,tables}/{id} routes directly.
const ME = "/api/v1/me";

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
  const scopeUserId = getScopeUserId();
  if (scopeUserId) {
    headers[SCOPE_HEADER] = scopeUserId;
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

// useAuth mounts in both the app layout and the page, so a cold load fires
// /users/me twice at once. Share the in-flight request; clear it once settled
// so later auth refreshes (login, cross-tab) re-fetch.
let _meInflight: Promise<User> | null = null;

export async function getMe(): Promise<User> {
  if (_meInflight) return _meInflight;
  _meInflight = apiFetch<User>("/api/v1/users/me").finally(() => {
    _meInflight = null;
  });
  return _meInflight;
}

// The workspaces the signed-in user belongs to — empty for most users. Sending
// a workspace's scope_user_id as X-Stash-Scope switches every scoped read and
// write to that workspace's shared knowledge base.
export async function listMyWorkspaces(): Promise<Workspace[]> {
  const data = await apiFetch<{ workspaces: Workspace[] }>(`${ME}/workspaces`);
  return data.workspaces;
}

export async function updateMe(data: {
  display_name?: string;
  description?: string;
  password?: string;
  current_password?: string;
  role?: string;
  referral_source?: string;
  use_case?: string;
  plan_intent?: string;
}): Promise<User> {
  return apiFetch("/api/v1/users/me", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// 'read' keys can read/search everything and upload session transcripts,
// nothing else — intended for production agents.
export type ApiKeyAccess = "read" | "full";

export interface ApiKeyInfo {
  id: string;
  name: string;
  access: ApiKeyAccess;
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
  access: ApiKeyAccess;
  api_key: string; // raw key — shown exactly once
  created_at: string;
}

export async function createMyKey(name: string, access: ApiKeyAccess): Promise<ApiKeyCreated> {
  return apiFetch("/api/v1/users/me/keys", {
    method: "POST",
    body: JSON.stringify({ name, access }),
  });
}

export async function searchUsers(query: string): Promise<UserSearchResult[]> {
  return apiFetch(`/api/v1/users/search?q=${encodeURIComponent(query)}`);
}

// --- Billing ---

export interface BillingInfo {
  billing_enabled: boolean;
  plan?: "free" | "pro";
  status?: string | null;
  connection_count?: number;
  connection_limit?: number;
}

export async function getBilling(): Promise<BillingInfo> {
  return apiFetch("/api/v1/billing/me");
}

export async function startCheckout(interval: "month" | "year"): Promise<{ url: string }> {
  return apiFetch("/api/v1/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ interval }),
  });
}

export async function openBillingPortal(): Promise<{ url: string }> {
  return apiFetch("/api/v1/billing/portal", { method: "POST" });
}

// --- Sources (connected integrations) ---

export interface Source {
  source: string; // native handle ("files"/"sessions") or connected-source id
  type: string; // 'native_files' | 'native_sessions' | 'github_repo' | ...
  capability: string; // 'navigable' | 'searchable'
  display_name: string;
  // Present for connected sources (the integration page uses these).
  external_ref?: string | null;
  sync_enabled?: boolean; // false for search-driven types (no indexer)
  sync_status?: string | null; // 'idle' | 'syncing' | 'failed'
  sync_error?: string | null;
  last_synced_at?: string | null;
  search_hint?: string | null;
  settings?: Record<string, unknown> | null;
}

export interface SourceStatus extends Source {
  item_count: number | null; // null for a source type with no document table
}

export interface SourceEntry {
  path?: string;
  id?: string;
  name: string;
  kind: string;
  external_ref?: string | null;
}

const NATIVE_SOURCE_TYPES = new Set(["native_files", "native_sessions"]);

export async function listSources(): Promise<Source[]> {
  const data = await apiFetch<{ sources: Source[] }>(`${ME}/sources`);
  // The sidebar's Sources section shows only connected sources; the native
  // file system and session transcripts already have their own sections.
  return data.sources.filter((s) => !NATIVE_SOURCE_TYPES.has(s.type));
}

export async function addSource(body: {
  source_type: string;
  external_ref?: string;
  display_name?: string;
  settings?: Record<string, unknown>;
}): Promise<{ id: string }> {
  return apiFetch(`${ME}/sources`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function syncSource(sourceId: string): Promise<{ task_id: string }> {
  return apiFetch(`${ME}/sources/${sourceId}/sync`, {
    method: "POST",
  });
}

export async function deleteSource(sourceId: string): Promise<void> {
  await apiFetch(`${ME}/sources/${sourceId}`, {
    method: "DELETE",
  });
}

// --- per-integration page: status + content browsing ---

export async function getSourceStatus(sourceId: string): Promise<SourceStatus> {
  return apiFetch(`${ME}/sources/${sourceId}/status`);
}

export async function getSourceEntries(
  source: string,
  path = "",
  opts: { limit?: number; after?: string } = {},
): Promise<SourceEntry[]> {
  const params = new URLSearchParams();
  if (path) params.set("path", path);
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.after) params.set("after", opts.after);
  const q = params.size ? `?${params}` : "";
  const data = await apiFetch<{ entries: SourceEntry[] }>(
    `${ME}/sources/${source}/entries${q}`,
  );
  return data.entries;
}

export async function readSourceDoc(
  source: string,
  ref: string,
): Promise<{ name?: string; content?: string; url?: string | null }> {
  return apiFetch(`${ME}/sources/${source}/doc?ref=${encodeURIComponent(ref)}`);
}

export interface SourceSearchHit {
  source: string;
  source_name?: string;
  // A real hit carries a ref; marker entries (see below) omit it.
  ref?: string;
  name?: string;
  snippet?: string;
  // Marker: a federated source hit its result cap — `returned` of ~`estimated_total`
  // matches are shown. `truncated` distinguishes it from a real hit.
  truncated?: boolean;
  returned?: number;
  estimated_total?: number | null;
}

export async function searchSource(
  query: string,
  source?: string,
): Promise<SourceSearchHit[]> {
  const params = new URLSearchParams({ q: query });
  if (source) params.set("source", source);
  const data = await apiFetch<{ results: SourceSearchHit[] }>(
    `${ME}/sources/search?${params.toString()}`,
  );
  return data.results;
}

export async function fetchSourceHistory(
  source: string,
  since: string,
  until?: string,
): Promise<{ fetched: number; since: string; until: string | null }> {
  return apiFetch(`${ME}/sources/${source}/history`, {
    method: "POST",
    body: JSON.stringify({ since, until }),
  });
}

// --- Discover (public catalog, no auth required) ---

// A public page from the pastebin (joinstash.ai/pages) — community docs/pages.
export interface PublicPageCard {
  slug: string;
  title: string;
  content_type: "markdown" | "html";
  view_count: number;
  created_at: string;
}

export async function listPublicPages(): Promise<PublicPageCard[]> {
  const res = await fetch(`${API_BASE}/api/v1/pastes`);
  if (!res.ok) return [];
  return (await res.json()).pastes ?? [];
}

export interface PublicSkillCard {
  id: string;
  slug: string;
  title: string;
  description: string;
  discoverable: boolean;
  cover_image_url: string | null;
  source_github_url: string | null;
  view_count: number;
  owner_name: string;
  owner_display_name: string;
  owner_user_id: string;
  item_count: number;
  created_at: string;
  updated_at: string;
}

// Skills imported from GitHub are owned by the curator account, but credit
// belongs to the repo owner — derive it from the attribution URL.
export function githubOwner(sourceGithubUrl: string): string {
  return sourceGithubUrl.replace("https://github.com/", "").split("/")[0];
}

// --- Files: folders (nested) and pages ---

export async function getTree(): Promise<Tree> {
  return apiFetch(`${ME}/tree`);
}

export async function listFolders(): Promise<{ folders: Folder[] }> {
  return apiFetch(`${ME}/folders`);
}

// The reserved per-user Memory folder (created on first access) — Memory's root.
export async function getMemoryFolder(): Promise<Folder> {
  return apiFetch(`${ME}/memory-folder`);
}

export interface WikiGraphNode {
  id: string;
  name: string;
  degree: number;
}

export interface WikiGraph {
  nodes: WikiGraphNode[];
  edges: { source: string; target: string }[];
}

// The Memory wiki as a graph: pages in the Memory subtree + links between them.
export async function getMemoryGraph(): Promise<WikiGraph> {
  return apiFetch(`${ME}/memory-graph`);
}

export async function createFolder(
  name: string,
  parentFolderId?: string | null
): Promise<Folder> {
  return apiFetch(`${ME}/folders`, {
    method: "POST",
    body: JSON.stringify({
      name,
      parent_folder_id: parentFolderId || null,
    }),
  });
}

export async function updateFolder(
  folderId: string,
  data: { name?: string; parent_folder_id?: string | null; move_to_root?: boolean }
): Promise<Folder> {
  return apiFetch(`${ME}/folders/${folderId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteFolder(folderId: string): Promise<void> {
  await apiFetch(`${ME}/folders/${folderId}`, { method: "DELETE" });
}

export async function createPage(
  name: string,
  folderId?: string | null,
  content?: string,
  options?: {
    content_type?: "markdown" | "html";
    content_html?: string;
    html_layout?: "responsive" | "fixed-aspect" | "full-width";
  }
): Promise<Page> {
  const page = await apiFetch<Page>(`${ME}/pages/new`, {
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
  trackEvent("web.page_created");
  return page;
}

export async function getPage(pageId: string): Promise<Page> {
  return apiFetch(`/api/v1/pages/${pageId}`);
}

export async function updatePage(
  pageId: string,
  data: {
    name?: string;
    folder_id?: string | null;
    content?: string;
    collab_projection?: boolean;
    content_type?: "markdown" | "html";
    content_html?: string;
    html_layout?: "responsive" | "fixed-aspect" | "full-width";
    move_to_root?: boolean;
  }
): Promise<Page> {
  const result = await apiFetch<Page>(`${ME}/pages/${pageId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
  // Only count actual content/title changes as "edits." Folder moves,
  // collab_projection passes, and pure layout flips are uninteresting.
  const isContentEdit =
    data.content !== undefined ||
    data.content_html !== undefined ||
    data.name !== undefined;
  if (isContentEdit) {
    trackEvent(
      "web.page_edited",
      { page_id: pageId },
      { dedupeKey: pageId, dedupeMs: 5 * 60 * 1000 },
    );
  }
  return result;
}

// --- Page comments ---

export async function listCommentThreads(
  pageId: string,
): Promise<{ threads: CommentThread[] }> {
  return apiFetch(`${ME}/pages/${pageId}/comments/threads`);
}

export async function createCommentThread(
  pageId: string,
  data: { quoted_text: string; prefix: string; suffix: string; body: string },
): Promise<CommentThread> {
  return apiFetch(`${ME}/pages/${pageId}/comments/threads`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function replyToCommentThread(
  pageId: string,
  threadId: string,
  body: string,
): Promise<CommentThread> {
  return apiFetch(
    `${ME}/pages/${pageId}/comments/threads/${threadId}/messages`,
    { method: "POST", body: JSON.stringify({ body }) },
  );
}

export async function setCommentResolved(
  pageId: string,
  threadId: string,
  resolved: boolean,
): Promise<CommentThread> {
  return apiFetch(
    `${ME}/pages/${pageId}/comments/threads/${threadId}`,
    { method: "PATCH", body: JSON.stringify({ resolved }) },
  );
}

export async function deleteCommentThread(
  pageId: string,
  threadId: string,
): Promise<void> {
  await apiFetch(
    `${ME}/pages/${pageId}/comments/threads/${threadId}`,
    { method: "DELETE" },
  );
}

export async function deleteCommentMessage(
  pageId: string,
  messageId: string,
): Promise<{ thread: CommentThread | null; thread_deleted: boolean }> {
  return apiFetch(
    `${ME}/pages/${pageId}/comments/messages/${messageId}`,
    { method: "DELETE" },
  );
}

export async function reconcileCommentAnchors(
  pageId: string,
  presentIds: string[],
): Promise<void> {
  await apiFetch(
    `${ME}/pages/${pageId}/comments/reconcile`,
    { method: "POST", body: JSON.stringify({ present_ids: presentIds }) },
  );
}

// --- Aggregate ---

// Flat page list for page pickers and search surfaces.
export async function listAllPages(): Promise<{ pages: UserPageEntry[] }> {
  return apiFetch(`${ME}/pages`);
}

export interface UserPageEntry {
  id: string;
  name: string;
  content_type: "markdown" | "html";
  owner_user_id: string;
  folder_id: string | null;
  folder_path: string[];
  updated_at: string;
}

export async function listAllTables(): Promise<{ tables: TableWithOwner[] }> {
  return apiFetch(`${ME}/tables`);
}

// --- Dashboard Visualizations ---

export interface MeOverview {
  pages: number;
  files: number;
  sessions: number;
}

// Counts for the "Your brain" vitals, spanning the user's own content plus
// everything shared with them.
export async function getMeOverview(): Promise<MeOverview> {
  return apiFetch(`${ME}/vitals`);
}

export async function getActivityTimeline(
  days = 30,
  bucket = "day",
): Promise<ActivityTimeline> {
  return apiFetch(`${ME}/activity-timeline?days=${days}&bucket=${bucket}`);
}

export async function getKnowledgeDensity(
  maxClusters = 20,
): Promise<KnowledgeDensity> {
  return apiFetch(`${ME}/knowledge-density?max_clusters=${maxClusters}`);
}

export async function getEmbeddingProjection(
  maxPoints = 500,
  source?: string,
): Promise<EmbeddingProjection> {
  const src = source ? `&source=${source}` : "";
  return apiFetch(`${ME}/embedding-projection?max_points=${maxPoints}${src}`);
}

// --- Tables ---

export async function createTable(
  name: string,
  description?: string,
  columns?: { name: string; type: string; options?: string[]; width?: number }[]
): Promise<Table> {
  return apiFetch(`${ME}/tables`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || "", columns: columns || [] }),
  });
}

export async function listTables(): Promise<{ tables: Table[] }> {
  return apiFetch(`${ME}/tables`);
}

export async function getTable(tableId: string): Promise<Table> {
  return apiFetch(`/api/v1/tables/${tableId}`);
}

export async function updateTable(
  tableId: string,
  data: { name?: string; description?: string; folder_id?: string | null; move_to_root?: boolean }
): Promise<Table> {
  return apiFetch(`${ME}/tables/${tableId}`, {
    method: "PATCH", body: JSON.stringify(data),
  });
}

export async function deleteTable(tableId: string): Promise<void> {
  await apiFetch(`${ME}/tables/${tableId}`, { method: "DELETE" });
}

// --- Table Columns ---

export async function addTableColumn(
  tableId: string,
  column: { name: string; type: string; required?: boolean; default?: unknown; options?: string[]; width?: number }
): Promise<Table> {
  return apiFetch(`${ME}/tables/${tableId}/columns`, {
    method: "POST", body: JSON.stringify(column),
  });
}

export async function updateTableColumn(
  tableId: string,
  columnId: string,
  updates: { name?: string; type?: string; required?: boolean; default?: unknown; options?: string[]; width?: number }
): Promise<Table> {
  return apiFetch(`${ME}/tables/${tableId}/columns/${columnId}`, {
    method: "PATCH", body: JSON.stringify(updates),
  });
}

export async function deleteTableColumn(
  tableId: string,
  columnId: string
): Promise<Table> {
  return apiFetch(`${ME}/tables/${tableId}/columns/${columnId}`, { method: "DELETE" });
}

export async function reorderTableColumns(
  tableId: string,
  columnIds: string[]
): Promise<Table> {
  return apiFetch(`${ME}/tables/${tableId}/columns/reorder`, {
    method: "PUT", body: JSON.stringify({ column_ids: columnIds }),
  });
}

// --- Table Rows ---

export async function listTableRows(
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
  return apiFetch(`${ME}/tables/${tableId}/rows${qs ? "?" + qs : ""}`);
}

export async function createTableRow(
  tableId: string,
  data: Record<string, unknown>
): Promise<TableRow> {
  return apiFetch(`${ME}/tables/${tableId}/rows`, {
    method: "POST", body: JSON.stringify({ data }),
  });
}

export async function createTableRowsBatch(
  tableId: string,
  rows: { data: Record<string, unknown> }[]
): Promise<{ rows: TableRow[] }> {
  return apiFetch(`${ME}/tables/${tableId}/rows/batch`, {
    method: "POST", body: JSON.stringify({ rows }),
  });
}

export async function updateTableRow(
  tableId: string,
  rowId: string,
  data: Record<string, unknown>
): Promise<TableRow> {
  return apiFetch(`${ME}/tables/${tableId}/rows/${rowId}`, {
    method: "PATCH", body: JSON.stringify({ data }),
  });
}

export async function deleteTableRow(
  tableId: string,
  rowId: string
): Promise<void> {
  await apiFetch(`${ME}/tables/${tableId}/rows/${rowId}`, { method: "DELETE" });
}

export async function deleteTableRowsBatch(
  tableId: string,
  rowIds: string[]
): Promise<{ deleted: number }> {
  return apiFetch(`${ME}/tables/${tableId}/rows/delete`, {
    method: "POST", body: JSON.stringify({ row_ids: rowIds }),
  });
}

// --- Table Search, Summary, Duplicate ---

export async function searchTableRows(
  tableId: string,
  query: string,
  params?: { limit?: number; offset?: number }
): Promise<{ rows: TableRow[]; total_count: number; has_more: boolean }> {
  const qs = new URLSearchParams({ q: query });
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  return apiFetch(`${ME}/tables/${tableId}/rows/search?${qs}`);
}

export async function summarizeTableRows(
  tableId: string,
  filters?: object[]
): Promise<{ total_rows: number; columns: Record<string, { name: string; filled: number; sum?: number; avg?: number; min?: number; max?: number }> }> {
  const qs = new URLSearchParams();
  if (filters && filters.length > 0) qs.set("filters", JSON.stringify(filters));
  const qsStr = qs.toString();
  return apiFetch(`${ME}/tables/${tableId}/rows/summary${qsStr ? "?" + qsStr : ""}`);
}

export async function duplicateTableRow(
  tableId: string,
  rowId: string
): Promise<TableRow> {
  return apiFetch(`${ME}/tables/${tableId}/rows/${rowId}/duplicate`, { method: "POST" });
}

// --- Table Views ---

export async function saveTableView(
  tableId: string,
  layout: { id?: string; name: string; filters?: object[]; sort_by?: string; sort_order?: string; visible_columns?: string[] }
): Promise<Table> {
  return apiFetch(`${ME}/tables/${tableId}/views`, {
    method: "POST", body: JSON.stringify(layout),
  });
}

export async function deleteTableView(
  tableId: string,
  viewId: string
): Promise<Table> {
  return apiFetch(`${ME}/tables/${tableId}/views/${viewId}`, { method: "DELETE" });
}

// --- Files ---

export function fileDownloadUrl(fileId: string): string {
  return `${ME}/files/${fileId}/download`;
}

// Raw response shape from POST /me/files. Polymorphic: the server routes
// .md/.html to the pages table (editable, commentable) and everything else
// to the files table (S3 blob). Discriminated by `kind`.
type UploadApiResponse = {
  kind: "file" | "page";
  id: string;
  owner_user_id: string;
  folder_id: string | null;
  owner_page_id: string | null;
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

// Matches MAX_FILE_SIZE in backend/routers/files.py and the Next proxy
// limit in next.config.ts. Rejecting here gives an instant, clear error
// instead of uploading for many seconds and failing downstream.
export const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;

async function uploadAny(
  file: File,
  folderId?: string | null
): Promise<UploadApiResponse> {
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new Error(`${file.name} is too large (max 100 MB)`);
  }
  const token = await getAuthToken();
  const formData = new FormData();
  formData.append("file", file);
  if (folderId) formData.append("folder_id", folderId);
  const resp = await fetch(`${API_BASE}${ME}/files`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!resp.ok) {
    const detail = await resp.json().then((d) => d.detail).catch(() => resp.statusText);
    throw new Error(detail);
  }
  const result = (await resp.json()) as UploadApiResponse;
  trackEvent("web.file_uploaded", {
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
  file: File,
  folderId?: string | null
): Promise<FileInfo> {
  const result = await uploadAny(file, folderId);
  if (result.kind === "page") {
    throw new Error(
      `uploadFile got a page back from the server (${file.name}); ` +
        `use uploadFileOrPage for content that may be markdown or HTML.`
    );
  }
  return {
    id: result.id,
    owner_user_id: result.owner_user_id,
    folder_id: result.folder_id,
    owner_page_id: result.owner_page_id,
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
  file: File,
  folderId?: string | null
): Promise<UploadResult> {
  const result = await uploadAny(file, folderId);
  if (result.kind === "page") {
    const page: Page = {
      id: result.id,
      owner_user_id: result.owner_user_id,
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
    owner_user_id: result.owner_user_id,
    folder_id: result.folder_id,
    owner_page_id: result.owner_page_id,
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

export async function listFiles(): Promise<FileInfo[]> {
  const data = await apiFetch<{ files: FileInfo[] }>(`${ME}/files`);
  return data.files;
}

export async function getFile(fileId: string): Promise<FileInfo> {
  return apiFetch(`/api/v1/files/${fileId}`);
}

export async function ingestCsvFile(fileId: string): Promise<Table> {
  return apiFetch(`${ME}/files/${fileId}/ingest-csv`, {
    method: "POST",
  });
}

export async function ingestXlsxFile(
  fileId: string,
): Promise<{ tables: Table[] }> {
  return apiFetch(`${ME}/files/${fileId}/ingest-xlsx`, {
    method: "POST",
  });
}

export async function updateFile(
  fileId: string,
  data: { folder_id?: string | null; move_to_root?: boolean; name?: string }
): Promise<FileInfo> {
  return apiFetch(`${ME}/files/${fileId}`, {
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
  owner_user_id: string | null;
  user_name: string;
  agent_name: string | null;
  event_count: number;
  started_at: string;
  last_event_at: string;
  session_folder_id: string | null;
  session_folder_name: string | null;
}

export type GeneralPermission = "none" | "read" | "comment" | "write";
// Stored visibility is two-state. "shared" is a derived display state.
export type SessionFolderVisibility = "private" | "public";
export type DisplayVisibility = "private" | "shared" | "public";

// The label to show: public link, else "shared" if anyone's been invited, else
// private. Session folders feed (access, count) in.
export function displayVisibility(
  access: "private" | "public",
  shareCount: number,
): DisplayVisibility {
  if (access === "public") return "public";
  return shareCount > 0 ? "shared" : "private";
}

export interface SessionFolder {
  id: string;
  owner_user_id: string;
  slug: string;
  name: string;
  owner_display_name: string | null;
  access: SessionFolderVisibility;
  public_permission: GeneralPermission;
  discoverable: boolean;
  is_default: boolean;
  view_count: number;
  session_count: number;
  share_count: number;
}

export async function listSessionFolders(): Promise<SessionFolder[]> {
  const data = await apiFetch<{ folders: SessionFolder[] }>(`${ME}/session-folders`);
  return data.folders;
}

export async function createSessionFolder(name: string): Promise<SessionFolder> {
  return apiFetch<SessionFolder>(`${ME}/session-folders`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function updateSessionFolder(
  folderId: string,
  data: {
    name?: string;
    public_permission?: GeneralPermission;
    discoverable?: boolean;
  },
): Promise<SessionFolder> {
  return apiFetch<SessionFolder>(
    `${ME}/session-folders/${folderId}`,
    { method: "PATCH", body: JSON.stringify(data) },
  );
}

export async function deleteSessionFolder(folderId: string): Promise<void> {
  await apiFetch(`${ME}/session-folders/${folderId}`, {
    method: "DELETE",
  });
}

// Move one or more sessions into a folder (or out, with folderId null).
export async function assignSessionFolder(
  sessionRowIds: string[],
  folderId: string | null,
): Promise<void> {
  await apiFetch(`${ME}/session-folders/assign`, {
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

export async function listMySessions(
  limit = 50,
  sessionFolderId?: string,
  offset = 0,
  agentChatsOnly = false
): Promise<SessionSummary[]> {
  const qs = new URLSearchParams();
  qs.set("limit", String(limit));
  if (offset) qs.set("offset", String(offset));
  if (sessionFolderId) qs.set("session_folder_id", sessionFolderId);
  if (agentChatsOnly) qs.set("agent_chats_only", "true");
  const data = await apiFetch<{ sessions: SessionSummary[] }>(
    `${ME}/sessions?${qs.toString()}`
  );
  return data.sessions;
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
  owner_user_id: string;
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

export async function getSessionDetail(sessionId: string): Promise<SessionDetail> {
  return apiFetch(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
}

export async function renameSession(
  sessionId: string,
  title: string
): Promise<{ title: string }> {
  return apiFetch(
    `${ME}/sessions/${encodeURIComponent(sessionId)}/title`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }
  );
}

export async function deleteSession(sessionRowId: string): Promise<void> {
  await apiFetch(`${ME}/sessions/${sessionRowId}`, {
    method: "DELETE",
  });
}

// Freeze a session transcript into a markdown page inside a folder — how
// sessions travel into skills (sessions can't live in folders directly).
export async function materializeSession(
  sessionId: string,
  folderId: string
): Promise<Page> {
  return apiFetch(
    `${ME}/sessions/${encodeURIComponent(sessionId)}/materialize`,
    { method: "POST", body: JSON.stringify({ folder_id: folderId }) },
  );
}

// --- Pins + recents (per user) ---

export type PinKind = "skills" | "sessions" | "files";

export interface Pins {
  skills: string[];
  sessions: string[];
  files: string[];
}

export interface RecentEntry {
  object_id: string;
  kind: string;
}

export async function getPins(): Promise<Pins> {
  return apiFetch(`${ME}/pins`);
}

export async function setPins(kind: PinKind, ids: string[]): Promise<void> {
  await apiFetch(`${ME}/pins/${kind}`, {
    method: "PUT",
    body: JSON.stringify({ ids }),
  });
}

// Recently-viewed objects (incl. shared items), most recent first.
export async function getMyRecents(): Promise<RecentEntry[]> {
  return apiFetch(`${ME}/recents`);
}

export async function recordRecent(
  objectId: string,
  kind: string
): Promise<void> {
  await apiFetch(`${ME}/recents`, {
    method: "POST",
    body: JSON.stringify({ object_id: objectId, kind }),
  });
}

// --- Skills (special folders with a SKILL.md, plus their publish records) ---

// The publish record on a skill folder. Published means publicly readable;
// null for skills that have never been published.
export interface SkillPublishInfo {
  id: string;
  slug: string;
  discoverable: boolean;
  cover_image_url: string | null;
  icon_url: string | null;
  view_count: number;
}

// A skill folder: SKILL.md frontmatter + folder stats + publish info.
export interface Skill {
  folder_id: string;
  name: string;
  description: string;
  when_to_use: string;
  version: string;
  mcp_exposed: boolean;
  file_count: number;
  updated_at: string;
  published: SkillPublishInfo | null;
}

export async function listSkills(): Promise<Skill[]> {
  const data = await apiFetch<{ skills: Skill[] }>(`${ME}/skills`);
  return data.skills;
}

// Import a public GitHub repo's SKILL.md folders as private skills in your scope.
export async function importGithubSkill(
  repoUrl: string,
): Promise<{ skills: number; imported: number }> {
  return apiFetch(`${ME}/skills/import-github`, {
    method: "POST",
    body: JSON.stringify({ repo_url: repoUrl }),
  });
}

// The full publish record, as returned by publish/update.
export interface PublishedSkill {
  id: string;
  owner_user_id: string;
  folder_id: string;
  slug: string;
  title: string;
  description: string;
  owner_id: string;
  owner_name: string;
  owner_display_name: string | null;
  discoverable: boolean;
  cover_image_url: string | null;
  icon_url: string | null;
  source_github_url: string | null;
  view_count: number;
  created_at: string;
  updated_at: string;
}

// Mint (or fetch) the publish record for a skill folder.
export async function publishSkillFolder(
  folderId: string,
  body: {
    title?: string;
    description?: string;
    discoverable?: boolean;
    cover_image_url?: string | null;
    icon_url?: string | null;
  } = {}
): Promise<PublishedSkill> {
  const skill = await apiFetch<PublishedSkill>(`${ME}/skills`, {
    method: "POST",
    body: JSON.stringify({ folder_id: folderId, ...body }),
  });
  trackEvent("web.skill_published");
  return skill;
}

// A skill folder someone shared with me person-to-person (a folder share on
// a folder that contains a SKILL.md). slug is set when it's also published.
export interface SharedSkill {
  folder_id: string;
  name: string;
  description: string;
  owner_user_id: string;
  shared_by: string | null;
  permission: "read" | "write";
  slug: string | null;
}

export async function listSkillsSharedWithMe(): Promise<SharedSkill[]> {
  const data = await apiFetch<{ skills: SharedSkill[] }>(`${ME}/shared-skills`);
  return data.skills;
}

// Inlined folder contents for the public skill renderer.
export interface PublicSkillSubfolder {
  id: string;
  name: string;
  parent_folder_id: string | null;
  path: string[];
}

export interface PublicSkillPage {
  id: string;
  name: string;
  content_type: "markdown" | "html";
  content_markdown: string;
  content_html: string;
  html_layout: "responsive" | "fixed-aspect" | "full-width";
  updated_at: string;
  folder_path: string[];
}

export interface PublicSkillFile {
  id: string;
  name: string;
  content_type: string;
  size_bytes: number;
  url: string;
  created_at: string;
  linked_table_id: string | null;
  folder_path: string[];
}

export interface PublicSkillTable {
  id: string;
  name: string;
  description: string;
  columns: { id?: string; name: string; type?: string }[];
  rows: { data: Record<string, unknown>; row_order: number }[];
  folder_path: string[];
}

export interface PublicSkillContents {
  subfolders: PublicSkillSubfolder[];
  pages: PublicSkillPage[];
  files: PublicSkillFile[];
  tables: PublicSkillTable[];
}

export interface PublicSkillDetail {
  skill: PublishedSkill;
  folder_name: string;
  contents: PublicSkillContents;
  can_write: boolean;
}

// Unpublish: deletes the publish record only — the folder stays a skill.
export async function unpublishSkill(skillId: string): Promise<void> {
  await apiFetch(`/api/v1/skills/${skillId}`, { method: "DELETE" });
}

export async function updateSkill(
  skillId: string,
  data: {
    title?: string;
    description?: string;
    discoverable?: boolean;
    cover_image_url?: string | null;
    icon_url?: string | null;
  }
): Promise<PublishedSkill> {
  return apiFetch(`/api/v1/skills/${skillId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function getPublicSkill(slug: string): Promise<PublicSkillDetail> {
  return apiFetch(`/api/v1/skills/${slug}`);
}

// Fork: deep folder copy into the caller's own space, landing as a private
// skill folder. The fork target is always the current user.
export async function forkSkill(
  slug: string
): Promise<{ folder_id: string; name: string }> {
  const me = await getMe();
  return apiFetch(`/api/v1/skills/${slug}/add-to-stash`, {
    method: "POST",
    body: JSON.stringify({ owner_user_id: me.id }),
  });
}

// --- Page index ---

export interface PageEntry {
  id: string;
  name: string;
  content_type: "markdown" | "html";
  owner_user_id: string;
  folder_id: string | null;
  // Chain of folder names from the root down to the page's folder.
  // Empty for pages at the root.
  folder_path: string[];
  updated_at: string;
}

export async function listPages(): Promise<PageEntry[]> {
  const data = await apiFetch<{ pages: PageEntry[] }>(`${ME}/pages`);
  return data.pages;
}

// --- Page semantic search ---

export async function semanticSearchPages(
  query: string,
  limit = 20
): Promise<Page[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const data = await apiFetch<{ pages: Page[] }>(
    `${ME}/pages/semantic-search?${params}`
  );
  return data.pages;
}

export async function searchPages(
  query: string,
  limit = 20
): Promise<Page[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const data = await apiFetch<{ pages: Page[] }>(
    `${ME}/pages/search?${params}`
  );
  return data.pages;
}

// --- Table Embeddings ---

export async function setTableEmbeddingConfig(
  tableId: string,
  config: { enabled: boolean; columns: string[] }
): Promise<Table> {
  return apiFetch<Table>(`${ME}/tables/${tableId}/embedding`, {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export async function backfillTableEmbeddings(
  tableId: string
): Promise<{ embedded: number; total: number }> {
  return apiFetch(`${ME}/tables/${tableId}/embedding/backfill`, {
    method: "POST",
  });
}

export async function semanticSearchTableRows(
  tableId: string,
  query: string,
  limit = 20
): Promise<TableRow[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const data = await apiFetch<{ rows: TableRow[] }>(
    `${ME}/tables/${tableId}/rows/semantic-search?${params}`
  );
  return data.rows;
}

// --- Agent Names ---

export async function listAgentNames(): Promise<string[]> {
  const data = await apiFetch<{ agent_names: string[] }>(
    `${ME}/sessions/agent-names`
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
  /** Agent that made the edit (e.g. the Memory curator); null = the edit
   *  didn't come through an agent session (a person, or setup/API writes). */
  agent_name: string | null;
}

export interface ActivityFeed {
  events: ActivityEvent[];
  has_more: boolean;
}

export async function listActivity(
  opts: { limit?: number; before?: string } = {}
): Promise<ActivityFeed> {
  const qs = new URLSearchParams({ limit: String(opts.limit ?? 50) });
  if (opts.before) qs.set("before", opts.before);
  return apiFetch(`${ME}/activity?${qs}`);
}

// --- Session transcripts ---

export interface SessionTranscript {
  id: string;
  owner_user_id: string;
  session_id: string;
  agent_name: string;
  size_bytes: number;
  cwd: string | null;
  uploaded_by: string;
  uploaded_at: string;
  download_url: string | null;
}

export async function getTranscript(sessionId: string): Promise<SessionTranscript> {
  return apiFetch(`${ME}/transcripts/${encodeURIComponent(sessionId)}`);
}

export interface SessionEvent {
  id: string;
  role: "user" | "assistant";
  agent_name: string;
  content: string;
  tool_name: string | null;
  created_at: string | null;
}

export interface SessionEventsPage {
  events: SessionEvent[];
  total: number;
  has_more: boolean;
}

export async function getSessionEventsPage(
  sessionId: string,
  limit = 100,
  offset = 0
): Promise<SessionEventsPage> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (offset) qs.set("offset", String(offset));
  return apiFetch<SessionEventsPage>(
    `${ME}/transcripts/${encodeURIComponent(sessionId)}/events?${qs}`
  );
}

// Drains every page. For consumers that search a whole session client-side;
// the viewer uses getSessionEventsPage directly for lazy loading.
export async function getSessionEvents(sessionId: string): Promise<SessionEvent[]> {
  const all: SessionEvent[] = [];
  let offset = 0;
  for (;;) {
    const page = await getSessionEventsPage(sessionId, 500, offset);
    all.push(...page.events);
    if (!page.has_more || page.events.length === 0) return all;
    offset += page.events.length;
  }
}

export interface HistoryEvent {
  id: string;
  owner_user_id: string;
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

export async function searchEvents(
  query: string,
  limit = 100
): Promise<HistoryEvent[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await apiFetch<{ events: HistoryEvent[] }>(
    `${ME}/sessions/events/search?${params}`
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

  const resp = await fetch(`${API_BASE}${ME}/transcripts`, {
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

// --- Overview, sessions, files, and skills ---

export interface SidebarSession {
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
export interface TreeFolder {
  id: string;
  name: string;
  parent_folder_id: string | null;
  page_count: number;
  file_count: number;
}
export interface TreePage {
  id: string;
  name: string;
  content_type: "markdown" | "html";
  folder_id: string | null;
}
export interface TreeFile {
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
export interface FilesTree {
  folders: TreeFolder[];
  pages: TreePage[];
  files: TreeFile[];
}

// Sidebar payload carries the unified skill-folder list (same shape as
// GET /me/skills items).
export type SidebarSkill = Skill;

export interface Overview {
  sessions: SidebarSession[];
  files: FilesTree;
  skills?: SidebarSkill[];
}

export async function getOverview(): Promise<Overview> {
  return apiFetch(`${ME}/overview`);
}

export interface Sidebar {
  sessions: SidebarSession[];
  files: FilesTree;
  skills?: SidebarSkill[];
}

// Cache the last ETag so revisiting the sidebar hits the cached payload
// instead of refetching.
let _sidebarEtag: string | null = null;
let _sidebarCache: Sidebar | null = null;

export async function getSidebar(): Promise<Sidebar> {
  const token = await getAuthToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (_sidebarEtag) headers["If-None-Match"] = _sidebarEtag;

  const res = await fetch(`${API_BASE}${ME}/sidebar`, {
    method: "GET",
    headers,
  });
  if (res.status === 304 && _sidebarCache) return _sidebarCache;
  if (!res.ok) throw new ApiError(res.status, `sidebar fetch failed: ${res.status}`);
  const etag = res.headers.get("etag");
  if (etag) _sidebarEtag = etag;
  const body = (await res.json()) as Sidebar;
  _sidebarCache = body;
  return body;
}

export interface FolderBreadcrumb {
  id: string;
  name: string;
  is_skill: boolean;
}
export interface FolderSubfolder {
  id: string;
  name: string;
  page_count: number;
  file_count: number;
  created_at: string;
}
export interface FolderContents {
  folder: { id: string; name: string; parent_folder_id: string | null; is_skill: boolean };
  breadcrumbs: FolderBreadcrumb[];
  subfolders: FolderSubfolder[];
  pages: { id: string; name: string; content_type: "markdown" | "html"; created_at: string }[];
  files: Omit<TreeFile, "folder_id">[];
  tables: { id: string; name: string; row_count: number; created_at: string }[];
}

export async function getFolderContents(folderId: string): Promise<FolderContents> {
  return apiFetch(`${ME}/folders/${folderId}/contents`);
}

// --- Shared with me ---

export type SharedObjectType =
  | "folder"
  | "session_folder"
  | "page"
  | "file"
  | "table"
  | "session"
  | "source";

export interface SharedWithMeItem {
  object_type: SharedObjectType;
  object_id: string;
  name: string;
  owner_user_id: string;
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

// The object's current "anyone with the link" level ('none' when it's only
// reachable by the owner and named shares).
export async function getGeneralAccess(
  objectType: SharedObjectType,
  objectId: string,
): Promise<GeneralPermission> {
  const res = await apiFetch<{ general_access: GeneralPermission }>(
    `/api/v1/share?object_type=${objectType}&object_id=${objectId}`,
  );
  return res.general_access;
}

export async function updateGeneralAccess(
  objectType: SharedObjectType,
  objectId: string,
  publicPermission: GeneralPermission,
): Promise<GeneralPermission> {
  const res = await apiFetch<{ public_permission: GeneralPermission }>(
    `/api/v1/share/general-access`,
    {
      method: "PATCH",
      body: JSON.stringify({
        object_type: objectType,
        object_id: objectId,
        public_permission: publicPermission,
      }),
    },
  );
  return res.public_permission;
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

export async function revokePendingShareInvite(
  objectType: SharedObjectType,
  objectId: string,
  email: string,
): Promise<void> {
  await apiFetch("/api/v1/share/invite", {
    method: "DELETE",
    body: JSON.stringify({
      object_type: objectType,
      object_id: objectId,
      email,
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

export async function trashItem(kind: TrashKind, id: string): Promise<void> {
  await apiFetch(`${ME}/${TRASH_KIND_PATH[kind]}/${id}`, { method: "DELETE" });
}

export async function restoreItem(kind: TrashKind, id: string): Promise<void> {
  await apiFetch(`${ME}/${TRASH_KIND_PATH[kind]}/${id}/restore`, { method: "POST" });
}

export async function purgeItem(kind: TrashKind, id: string): Promise<void> {
  await apiFetch(`${ME}/${TRASH_KIND_PATH[kind]}/${id}/purge`, { method: "DELETE" });
}

export async function getTrash(): Promise<TrashListing> {
  return apiFetch(`${ME}/trash`);
}

// ── The user's cloud computer (read-through projection; see routers/machine.py) ──

export type MachineEntry = { name: string; dir: boolean; size: number; mtime: number };

export async function machineFsList(path: string): Promise<MachineEntry[]> {
  const data = await apiFetch<{ entries: MachineEntry[] }>(
    `/api/v1/me/machine/fs?path=${encodeURIComponent(path)}`,
  );
  return data.entries;
}

export type MachineFile = { path: string; size: number; text?: string; content_base64?: string };

export async function machineFsRead(path: string): Promise<MachineFile> {
  return apiFetch<MachineFile>(`/api/v1/me/machine/fs/file?path=${encodeURIComponent(path)}`);
}

export async function machineSaveToStash(
  path: string,
  folderId?: string | null,
): Promise<{ kind: string; id: string; name: string; app_url: string }> {
  return apiFetch(`/api/v1/me/machine/fs/save-to-stash`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, folder_id: folderId ?? null }),
  });
}

// ── Cloud-agent model credentials (BYO key / OAuth; see routers/agent_credentials) ──

export async function listAgentCredentials(): Promise<string[]> {
  const data = await apiFetch<{ connected: string[] }>("/api/v1/me/agent-credentials");
  return data.connected;
}

export async function connectAgentKey(provider: string, apiKey: string): Promise<string[]> {
  const data = await apiFetch<{ connected: string[] }>("/api/v1/me/agent-credentials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, api_key: apiKey }),
  });
  return data.connected;
}

export async function disconnectAgentCredential(provider: string): Promise<string[]> {
  const data = await apiFetch<{ connected: string[] }>(
    `/api/v1/me/agent-credentials/${provider}`,
    { method: "DELETE" },
  );
  return data.connected;
}

export async function startAgentOAuth(
  provider: string,
): Promise<{ authorize_url: string; state: string }> {
  return apiFetch("/api/v1/me/agent-credentials/oauth/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
}

export async function finishAgentOAuth(
  provider: string,
  code: string,
  state: string,
): Promise<string[]> {
  const data = await apiFetch<{ connected: string[] }>(
    "/api/v1/me/agent-credentials/oauth/finish",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, code, state }),
    },
  );
  return data.connected;
}

// ── Named agents (config: model, persona, schedule, channel binding) ──

export type Agent = {
  id: string;
  name: string;
  model_provider: string | null;
  system_prompt: string | null;
  run_mode: string;
  schedule_cron: string | null;
  schedule_prompt: string | null;
  is_default: boolean;
  is_curator: boolean;
  slack_bound: boolean;
  telegram_bound: boolean;
  last_run_at: string | null;
  last_run_error: string | null;
  curated_through: string | null;
};

export async function listAgents(): Promise<Agent[]> {
  const data = await apiFetch<{ agents: Agent[] }>("/api/v1/me/agents");
  return data.agents;
}

/** Enqueue a curation pass on the worker — the same path the daily schedule
 *  and the CLI use, so the run survives the browser. 409 = nothing changed
 *  since the watermark. */
export async function recomputeMemory(): Promise<{ status: string; agent_id: string }> {
  return apiFetch("/api/v1/me/memory/recompute", { method: "POST" });
}

export async function createAgent(fields: Partial<Agent>): Promise<Agent> {
  return apiFetch("/api/v1/me/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export async function updateAgent(id: string, fields: Partial<Agent>): Promise<Agent> {
  return apiFetch(`/api/v1/me/agents/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export async function deleteAgent(id: string): Promise<void> {
  await apiFetch(`/api/v1/me/agents/${id}`, { method: "DELETE" });
}

export type AgentPrompt = { system_prompt: string; run_prompt: string };

export async function getAgentPrompt(id: string): Promise<AgentPrompt> {
  return apiFetch(`/api/v1/me/agents/${id}/prompt`);
}
