import {
  PersonaProfile,
  PersonaResponse,
  PersonaWithContext,
  Chat,
  ChatWithWorkspace,
  Deck,
  DeckShare,
  DeckWithWorkspace,
  DMWithUser,
  DMConversation,
  Document,
  DocumentChunk,
  FileInfo,
  HistoryEvent,
  HistoryEventWithContext,
  History,
  HistoryWithWorkspace,
  Message,
  Notebook,
  NotebookFolder,
  NotebookPage,
  NotebookWithWorkspace,
  PageGraph,
  PageLink,
  PageTree,
  ObjectPermission,
  RegisterResponse,
  SearchResponse,
  SleepConfig,
  User,
  UserSearchResult,
  Table,
  TableRow,
  TableWithWorkspace,
  Webhook,
  Workspace,
  WorkspaceMember,
} from "./types";

const TOKEN_KEY = "boozle_token";
const LEGACY_TOKEN_KEY = "moltchat_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY) || localStorage.getItem(LEGACY_TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.removeItem(LEGACY_TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(LEGACY_TOKEN_KEY);
}

const API_BASE = "";

/**
 * Build the WebSocket base URL.  Next.js rewrites proxy HTTP /api/* to the
 * backend but they cannot proxy WebSocket upgrades.  When the backend lives
 * on a separate origin (e.g. Render) we must connect directly.
 */
export function getWsBase(): string {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (apiUrl) {
    // Convert http(s) → ws(s)
    return apiUrl.replace(/^http/, "ws");
  }
  // Local dev — same host
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}`;
}

async function apiFetch<T>(
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
    throw new Error(body.detail || `API error ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// --- Users ---

export async function register(
  name: string,
  type: "human" | "persona",
  displayName?: string,
  description?: string,
  password?: string
): Promise<RegisterResponse> {
  return apiFetch("/api/v1/users/register", {
    method: "POST",
    body: JSON.stringify({
      name,
      type,
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
}): Promise<User> {
  return apiFetch("/api/v1/users/me", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
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

// --- Chats (within workspaces) ---

export async function createChat(
  workspaceId: string,
  name: string,
  description?: string
): Promise<Chat> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/chats`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
}

export async function listChats(workspaceId: string): Promise<{ chats: Chat[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/chats`);
}

export async function getChat(workspaceId: string, chatId: string): Promise<Chat> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/chats/${chatId}`);
}

export async function deleteChat(workspaceId: string, chatId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/chats/${chatId}`, { method: "DELETE" });
}

// --- Messages ---

export async function sendMessage(
  workspaceId: string,
  chatId: string,
  content: string,
  replyToId?: string
): Promise<Message> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content, reply_to_id: replyToId || null }),
  });
}

export async function getMessages(
  workspaceId: string,
  chatId: string,
  params?: { after?: string; before?: string; limit?: number }
): Promise<{ messages: Message[]; has_more: boolean }> {
  const searchParams = new URLSearchParams();
  if (params?.after) searchParams.set("after", params.after);
  if (params?.before) searchParams.set("before", params.before);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return apiFetch(`/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages${qs ? `?${qs}` : ""}`);
}

export async function searchMessages(
  workspaceId: string,
  chatId: string,
  query: string,
  limit?: number
): Promise<{ messages: Message[]; has_more: boolean }> {
  const searchParams = new URLSearchParams({ q: query });
  if (limit) searchParams.set("limit", String(limit));
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages/search?${searchParams.toString()}`
  );
}

// --- DMs ---

export async function sendDMMessage(chatId: string, content: string, replyToId?: string): Promise<Message> {
  return apiFetch(`/api/v1/dms/${chatId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content, reply_to_id: replyToId || null }),
  });
}

export async function getDMMessages(
  chatId: string,
  params?: { after?: string; limit?: number }
): Promise<{ messages: Message[]; has_more: boolean }> {
  const searchParams = new URLSearchParams();
  if (params?.after) searchParams.set("after", params.after);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return apiFetch(`/api/v1/dms/${chatId}/messages${qs ? `?${qs}` : ""}`);
}

export async function createOrGetDM(userId: string): Promise<DMConversation> {
  return apiFetch("/api/v1/dms", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function createOrGetDMByUsername(username: string): Promise<DMConversation> {
  return apiFetch("/api/v1/dms", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
}

export async function listDMs(): Promise<{ dms: DMConversation[] }> {
  return apiFetch("/api/v1/dms");
}

export async function searchUsers(query: string): Promise<UserSearchResult[]> {
  return apiFetch(`/api/v1/dms/users/search?q=${encodeURIComponent(query)}`);
}

// --- Notebooks (collections) ---

export async function listNotebooks(workspaceId: string): Promise<{ notebooks: Notebook[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks`);
}

export async function createNotebook(
  workspaceId: string,
  name: string,
  description?: string
): Promise<Notebook> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
}

export async function deleteNotebook(workspaceId: string, notebookId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}`, { method: "DELETE" });
}

// --- Notebook Pages (files within a notebook, workspace-scoped) ---

export async function listPageTree(workspaceId: string, notebookId: string): Promise<PageTree> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/pages`);
}

export async function createPage(
  workspaceId: string,
  notebookId: string,
  name: string,
  folderId?: string,
  content?: string
): Promise<NotebookPage> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/pages`, {
    method: "POST",
    body: JSON.stringify({ name, folder_id: folderId || null, content: content || "" }),
  });
}

export async function getPage(
  workspaceId: string, notebookId: string, pageId: string
): Promise<NotebookPage> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/pages/${pageId}`);
}

export async function updatePage(
  workspaceId: string, notebookId: string, pageId: string,
  data: { name?: string; folder_id?: string; content?: string; move_to_root?: boolean }
): Promise<NotebookPage> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/pages/${pageId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deletePage(
  workspaceId: string, notebookId: string, pageId: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/pages/${pageId}`, { method: "DELETE" });
}

export async function createPageFolder(
  workspaceId: string, notebookId: string, name: string
): Promise<NotebookFolder> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/folders`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renamePageFolder(
  workspaceId: string, notebookId: string, folderId: string, name: string
): Promise<NotebookFolder> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/folders/${folderId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deletePageFolder(
  workspaceId: string, notebookId: string, folderId: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/folders/${folderId}`, { method: "DELETE" });
}

// --- History ---

export async function createHistory(
  workspaceId: string,
  name: string,
  description?: string
): Promise<History> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/memory`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
}

export async function listHistories(workspaceId: string): Promise<{ stores: History[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/memory`);
}

export async function getHistory(workspaceId: string, storeId: string): Promise<History> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/memory/${storeId}`);
}

export async function queryHistoryEvents(
  workspaceId: string,
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
  return apiFetch(`/api/v1/workspaces/${workspaceId}/memory/${storeId}/events${qs ? `?${qs}` : ""}`);
}

export async function searchHistoryEvents(
  workspaceId: string,
  storeId: string,
  query: string,
  limit?: number
): Promise<{ events: HistoryEvent[]; has_more: boolean }> {
  const searchParams = new URLSearchParams({ q: query });
  if (limit) searchParams.set("limit", String(limit));
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/memory/${storeId}/events/search?${searchParams.toString()}`
  );
}

export async function queryHistory(
  workspaceId: string,
  storeId: string,
  question: string,
): Promise<{ answer: string; sources: HistoryEvent[] }> {
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/memory/${storeId}/query`,
    {
      method: "POST",
      body: JSON.stringify({ question }),
    }
  );
}

// --- Personal Rooms ---

export async function createPersonalRoom(
  name: string,
  description?: string
): Promise<Chat> {
  return apiFetch("/api/v1/rooms", {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
}

export async function listPersonalRooms(): Promise<{ chats: Chat[] }> {
  return apiFetch("/api/v1/rooms");
}

export async function getPersonalRoom(chatId: string): Promise<Chat> {
  return apiFetch(`/api/v1/rooms/${chatId}`);
}

export async function deletePersonalRoom(chatId: string): Promise<void> {
  await apiFetch(`/api/v1/rooms/${chatId}`, { method: "DELETE" });
}

export async function sendPersonalRoomMessage(
  chatId: string,
  content: string,
  replyToId?: string
): Promise<Message> {
  return apiFetch(`/api/v1/rooms/${chatId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content, reply_to_id: replyToId || null }),
  });
}

export async function getPersonalRoomMessages(
  chatId: string,
  params?: { after?: string; before?: string; limit?: number }
): Promise<{ messages: Message[]; has_more: boolean }> {
  const searchParams = new URLSearchParams();
  if (params?.after) searchParams.set("after", params.after);
  if (params?.before) searchParams.set("before", params.before);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return apiFetch(`/api/v1/rooms/${chatId}/messages${qs ? `?${qs}` : ""}`);
}

// --- Personal Notebooks ---

export async function listPersonalNotebooks(): Promise<{ notebooks: Notebook[] }> {
  return apiFetch("/api/v1/notebooks");
}

export async function createPersonalNotebook(
  name: string,
  description?: string
): Promise<Notebook> {
  return apiFetch("/api/v1/notebooks", {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
}

export async function deletePersonalNotebook(notebookId: string): Promise<void> {
  await apiFetch(`/api/v1/notebooks/${notebookId}`, { method: "DELETE" });
}

// --- Personal Notebook Pages ---

export async function listPersonalPageTree(notebookId: string): Promise<PageTree> {
  return apiFetch(`/api/v1/notebooks/${notebookId}/pages`);
}

export async function createPersonalPage(
  notebookId: string, name: string, folderId?: string, content?: string
): Promise<NotebookPage> {
  return apiFetch(`/api/v1/notebooks/${notebookId}/pages`, {
    method: "POST",
    body: JSON.stringify({ name, folder_id: folderId || null, content: content || "" }),
  });
}

export async function getPersonalPage(notebookId: string, pageId: string): Promise<NotebookPage> {
  return apiFetch(`/api/v1/notebooks/${notebookId}/pages/${pageId}`);
}

export async function updatePersonalPage(
  notebookId: string, pageId: string,
  data: { name?: string; folder_id?: string; content?: string; move_to_root?: boolean }
): Promise<NotebookPage> {
  return apiFetch(`/api/v1/notebooks/${notebookId}/pages/${pageId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deletePersonalPage(notebookId: string, pageId: string): Promise<void> {
  await apiFetch(`/api/v1/notebooks/${notebookId}/pages/${pageId}`, { method: "DELETE" });
}

export async function createPersonalPageFolder(notebookId: string, name: string): Promise<NotebookFolder> {
  return apiFetch(`/api/v1/notebooks/${notebookId}/folders`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renamePersonalPageFolder(
  notebookId: string, folderId: string, name: string
): Promise<NotebookFolder> {
  return apiFetch(`/api/v1/notebooks/${notebookId}/folders/${folderId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deletePersonalPageFolder(notebookId: string, folderId: string): Promise<void> {
  await apiFetch(`/api/v1/notebooks/${notebookId}/folders/${folderId}`, { method: "DELETE" });
}

// --- Personal Memory ---

export async function createPersonalHistory(
  name: string,
  description?: string
): Promise<History> {
  return apiFetch("/api/v1/memory", {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
}

export async function listPersonalHistories(): Promise<{ stores: History[] }> {
  return apiFetch("/api/v1/memory");
}

export async function getPersonalHistory(storeId: string): Promise<History> {
  return apiFetch(`/api/v1/memory/${storeId}`);
}

export async function deletePersonalHistory(storeId: string): Promise<void> {
  await apiFetch(`/api/v1/memory/${storeId}`, { method: "DELETE" });
}

export async function pushPersonalHistoryEvent(
  storeId: string,
  event: {
    agent_name: string;
    event_type: string;
    content: string;
    session_id?: string;
    tool_name?: string;
    metadata?: Record<string, unknown>;
  }
): Promise<HistoryEvent> {
  return apiFetch(`/api/v1/memory/${storeId}/events`, {
    method: "POST",
    body: JSON.stringify(event),
  });
}

export async function queryPersonalHistoryEvents(
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
  return apiFetch(`/api/v1/memory/${storeId}/events${qs ? `?${qs}` : ""}`);
}

export async function searchPersonalHistoryEvents(
  storeId: string,
  query: string,
  limit?: number
): Promise<{ events: HistoryEvent[]; has_more: boolean }> {
  const searchParams = new URLSearchParams({ q: query });
  if (limit) searchParams.set("limit", String(limit));
  return apiFetch(
    `/api/v1/memory/${storeId}/events/search?${searchParams.toString()}`
  );
}

// --- Aggregate (cross-workspace) ---

export async function listAllChats(): Promise<{ chats: ChatWithWorkspace[]; dms: DMWithUser[] }> {
  return apiFetch("/api/v1/me/chats");
}

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

export async function listPersonasWithContext(): Promise<{ personas: PersonaWithContext[] }> {
  return apiFetch("/api/v1/me/personas");
}

export async function listPersonas(workspaceId?: string): Promise<PersonaProfile[]> {
  const qs = workspaceId ? `?ws=${workspaceId}` : "";
  return apiFetch<PersonaProfile[]>(`/api/v1/personas${qs}`);
}

// --- Decks (workspace-scoped) ---

export async function createDeck(
  workspaceId: string, name: string, description?: string,
  htmlContent?: string, deckType?: string
): Promise<Deck> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/decks`, {
    method: "POST",
    body: JSON.stringify({
      name, description: description || "", html_content: htmlContent || "",
      deck_type: deckType || "freeform",
    }),
  });
}

export async function listDecks(workspaceId: string): Promise<{ decks: Deck[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/decks`);
}

export async function getDeck(workspaceId: string, deckId: string): Promise<Deck> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/decks/${deckId}`);
}

export async function updateDeck(
  workspaceId: string, deckId: string,
  data: { name?: string; description?: string; html_content?: string }
): Promise<Deck> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/decks/${deckId}`, {
    method: "PATCH", body: JSON.stringify(data),
  });
}

export async function deleteDeck(workspaceId: string, deckId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/decks/${deckId}`, { method: "DELETE" });
}

// --- Personal Decks ---

export async function createPersonalDeck(
  name: string, description?: string, htmlContent?: string, deckType?: string
): Promise<Deck> {
  return apiFetch("/api/v1/decks", {
    method: "POST",
    body: JSON.stringify({
      name, description: description || "", html_content: htmlContent || "",
      deck_type: deckType || "freeform",
    }),
  });
}

export async function listPersonalDecks(): Promise<{ decks: Deck[] }> {
  return apiFetch("/api/v1/decks");
}

export async function getPersonalDeck(deckId: string): Promise<Deck> {
  return apiFetch(`/api/v1/decks/${deckId}`);
}

export async function updatePersonalDeck(
  deckId: string, data: { name?: string; description?: string; html_content?: string }
): Promise<Deck> {
  return apiFetch(`/api/v1/decks/${deckId}`, { method: "PATCH", body: JSON.stringify(data) });
}

export async function deletePersonalDeck(deckId: string): Promise<void> {
  await apiFetch(`/api/v1/decks/${deckId}`, { method: "DELETE" });
}

// --- Deck Share Links ---

export async function createDeckShare(
  deckId: string, workspaceId?: string,
  data?: { name?: string; require_email?: boolean; passcode?: string; allow_download?: boolean; expires_at?: string }
): Promise<DeckShare> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/decks` : "/api/v1/decks";
  return apiFetch(`${base}/${deckId}/shares`, { method: "POST", body: JSON.stringify(data || {}) });
}

export async function listDeckShares(deckId: string, workspaceId?: string): Promise<{ shares: DeckShare[] }> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/decks` : "/api/v1/decks";
  return apiFetch(`${base}/${deckId}/shares`);
}

// --- Public Deck Viewer ---

export async function getDeckByToken(token: string): Promise<{ deck_name: string; deck_type: string; require_email: boolean; has_passcode: boolean; allow_download: boolean }> {
  return apiFetch(`/api/v1/d/${token}`);
}

export async function getDeckContent(token: string): Promise<{ html_content: string; deck_name: string; deck_type: string; session_token: string }> {
  return apiFetch(`/api/v1/d/${token}/content`);
}

export async function verifyDeckAccess(token: string, email?: string, passcode?: string): Promise<{ html_content: string; deck_name: string; deck_type: string; session_token: string }> {
  return apiFetch(`/api/v1/d/${token}/verify`, {
    method: "POST", body: JSON.stringify({ email, passcode }),
  });
}

// --- Aggregate Decks ---

export async function listAllDecks(): Promise<{ decks: DeckWithWorkspace[] }> {
  return apiFetch("/api/v1/me/decks");
}

// --- Tables (workspace-scoped) ---

export async function createTable(
  workspaceId: string, name: string, description?: string,
  columns?: { name: string; type: string; options?: string[] }[]
): Promise<Table> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/tables`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || "", columns: columns || [] }),
  });
}

export async function listTables(workspaceId: string): Promise<{ tables: Table[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/tables`);
}

export async function getTable(workspaceId: string, tableId: string): Promise<Table> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/tables/${tableId}`);
}

export async function updateTable(
  workspaceId: string, tableId: string,
  data: { name?: string; description?: string }
): Promise<Table> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/tables/${tableId}`, {
    method: "PATCH", body: JSON.stringify(data),
  });
}

export async function deleteTable(workspaceId: string, tableId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/tables/${tableId}`, { method: "DELETE" });
}

// --- Table Columns ---

export async function addTableColumn(
  tableId: string, column: { name: string; type: string; required?: boolean; default?: unknown; options?: string[] },
  workspaceId?: string
): Promise<Table> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/columns`, {
    method: "POST", body: JSON.stringify(column),
  });
}

export async function updateTableColumn(
  tableId: string, columnId: string,
  updates: { name?: string; type?: string; required?: boolean; default?: unknown; options?: string[] },
  workspaceId?: string
): Promise<Table> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/columns/${columnId}`, {
    method: "PATCH", body: JSON.stringify(updates),
  });
}

export async function deleteTableColumn(
  tableId: string, columnId: string, workspaceId?: string
): Promise<Table> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/columns/${columnId}`, { method: "DELETE" });
}

export async function reorderTableColumns(
  tableId: string, columnIds: string[], workspaceId?: string
): Promise<Table> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/columns/reorder`, {
    method: "PUT", body: JSON.stringify({ column_ids: columnIds }),
  });
}

// --- Table Rows ---

export async function listTableRows(
  tableId: string,
  params?: { sort_by?: string; sort_order?: string; limit?: number; offset?: number; filters?: object[] },
  workspaceId?: string
): Promise<{ rows: TableRow[]; total_count: number; has_more: boolean }> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  const query = new URLSearchParams();
  if (params?.sort_by) query.set("sort_by", params.sort_by);
  if (params?.sort_order) query.set("sort_order", params.sort_order);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  if (params?.filters) query.set("filters", JSON.stringify(params.filters));
  const qs = query.toString();
  return apiFetch(`${base}/${tableId}/rows${qs ? "?" + qs : ""}`);
}

export async function createTableRow(
  tableId: string, data: Record<string, unknown>, workspaceId?: string
): Promise<TableRow> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/rows`, {
    method: "POST", body: JSON.stringify({ data }),
  });
}

export async function createTableRowsBatch(
  tableId: string, rows: { data: Record<string, unknown> }[], workspaceId?: string
): Promise<{ rows: TableRow[] }> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/rows/batch`, {
    method: "POST", body: JSON.stringify({ rows }),
  });
}

export async function updateTableRow(
  tableId: string, rowId: string, data: Record<string, unknown>, workspaceId?: string
): Promise<TableRow> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/rows/${rowId}`, {
    method: "PATCH", body: JSON.stringify({ data }),
  });
}

export async function deleteTableRow(
  tableId: string, rowId: string, workspaceId?: string
): Promise<void> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  await apiFetch(`${base}/${tableId}/rows/${rowId}`, { method: "DELETE" });
}

export async function deleteTableRowsBatch(
  tableId: string, rowIds: string[], workspaceId?: string
): Promise<{ deleted: number }> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/rows/delete`, {
    method: "POST", body: JSON.stringify({ row_ids: rowIds }),
  });
}

// --- Personal Tables ---

export async function createPersonalTable(
  name: string, description?: string,
  columns?: { name: string; type: string; options?: string[] }[]
): Promise<Table> {
  return apiFetch("/api/v1/tables", {
    method: "POST",
    body: JSON.stringify({ name, description: description || "", columns: columns || [] }),
  });
}

export async function listPersonalTables(): Promise<{ tables: Table[] }> {
  return apiFetch("/api/v1/tables");
}

export async function getPersonalTable(tableId: string): Promise<Table> {
  return apiFetch(`/api/v1/tables/${tableId}`);
}

export async function updatePersonalTable(
  tableId: string, data: { name?: string; description?: string }
): Promise<Table> {
  return apiFetch(`/api/v1/tables/${tableId}`, { method: "PATCH", body: JSON.stringify(data) });
}

export async function deletePersonalTable(tableId: string): Promise<void> {
  await apiFetch(`/api/v1/tables/${tableId}`, { method: "DELETE" });
}

// --- Table Search, Summary, Duplicate ---

export async function searchTableRows(
  tableId: string, query: string, params?: { limit?: number; offset?: number }, workspaceId?: string
): Promise<{ rows: TableRow[]; total_count: number; has_more: boolean }> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  const qs = new URLSearchParams({ q: query });
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  return apiFetch(`${base}/${tableId}/rows/search?${qs}`);
}

export async function summarizeTableRows(
  tableId: string, filters?: object[], workspaceId?: string
): Promise<{ total_rows: number; columns: Record<string, { name: string; filled: number; sum?: number; avg?: number; min?: number; max?: number }> }> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  const qs = new URLSearchParams();
  if (filters && filters.length > 0) qs.set("filters", JSON.stringify(filters));
  const qsStr = qs.toString();
  return apiFetch(`${base}/${tableId}/rows/summary${qsStr ? "?" + qsStr : ""}`);
}

export async function duplicateTableRow(
  tableId: string, rowId: string, workspaceId?: string
): Promise<TableRow> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/rows/${rowId}/duplicate`, { method: "POST" });
}

// --- Table Views ---

export async function saveTableView(
  tableId: string, view: { id?: string; name: string; filters?: object[]; sort_by?: string; sort_order?: string; visible_columns?: string[] },
  workspaceId?: string
): Promise<Table> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/views`, { method: "POST", body: JSON.stringify(view) });
}

export async function deleteTableView(
  tableId: string, viewId: string, workspaceId?: string
): Promise<Table> {
  const base = workspaceId ? `/api/v1/workspaces/${workspaceId}/tables` : "/api/v1/tables";
  return apiFetch(`${base}/${tableId}/views/${viewId}`, { method: "DELETE" });
}

// --- Aggregate Tables ---

export async function listAllTables(): Promise<{ tables: TableWithWorkspace[] }> {
  return apiFetch("/api/v1/me/tables");
}

// --- Webhooks ---

export async function getWebhook(workspaceId: string): Promise<Webhook | null> {
  try {
    return await apiFetch(`/api/v1/workspaces/${workspaceId}/webhooks`);
  } catch {
    return null;
  }
}

export async function setWebhook(
  workspaceId: string, url: string, secret?: string, eventFilter?: string[]
): Promise<Webhook> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/webhooks`, {
    method: "POST",
    body: JSON.stringify({ url, secret: secret || undefined, event_filter: eventFilter || [] }),
  });
}

export async function updateWebhook(
  workspaceId: string, data: { url?: string; is_active?: boolean; event_filter?: string[] }
): Promise<Webhook> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/webhooks`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteWebhook(workspaceId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/webhooks`, { method: "DELETE" });
}

// --- Personas ---

export async function createPersona(
  name: string,
  displayName?: string,
  description?: string,
  workspaceId?: string,
): Promise<PersonaResponse> {
  return apiFetch("/api/v1/personas", {
    method: "POST",
    body: JSON.stringify({
      name,
      display_name: displayName || null,
      description: description || "",
      workspace_id: workspaceId || null,
    }),
  });
}

export async function updatePersona(
  personaId: string,
  data: { display_name?: string; description?: string }
): Promise<PersonaProfile> {
  return apiFetch(`/api/v1/personas/${personaId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function rotatePersonaKey(personaId: string): Promise<PersonaResponse> {
  return apiFetch(`/api/v1/personas/${personaId}/rotate-key`, { method: "POST" });
}

export async function deletePersona(personaId: string): Promise<void> {
  await apiFetch(`/api/v1/personas/${personaId}`, { method: "DELETE" });
}

// --- Permissions ---

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

export async function uploadFile(workspaceId: string, file: File): Promise<FileInfo> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${API_BASE}/api/v1/workspaces/${workspaceId}/files`, {
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

export async function uploadPersonalFile(file: File): Promise<FileInfo> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${API_BASE}/api/v1/files`, {
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

export async function listFiles(workspaceId: string): Promise<FileInfo[]> {
  const data = await apiFetch<{ files: FileInfo[] }>(`/api/v1/workspaces/${workspaceId}/files`);
  return data.files;
}

export async function deleteFile(workspaceId: string, fileId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}`, { method: "DELETE" });
}

// --- Documents ---

export async function uploadDocument(workspaceId: string, file: File): Promise<Document> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${API_BASE}/api/v1/workspaces/${workspaceId}/documents`, {
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

export async function listDocuments(
  workspaceId: string,
  status?: string
): Promise<Document[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const qs = params.toString();
  const data = await apiFetch<{ documents: Document[] }>(
    `/api/v1/workspaces/${workspaceId}/documents${qs ? `?${qs}` : ""}`
  );
  return data.documents;
}

export async function getDocument(workspaceId: string, docId: string): Promise<Document> {
  return apiFetch<Document>(`/api/v1/workspaces/${workspaceId}/documents/${docId}`);
}

export async function searchDocuments(
  workspaceId: string,
  query: string,
  limit = 20
): Promise<DocumentChunk[]> {
  const data = await apiFetch<{ chunks: DocumentChunk[] }>(
    `/api/v1/workspaces/${workspaceId}/documents/search`,
    { method: "POST", body: JSON.stringify({ query, limit }) }
  );
  return data.chunks;
}

export async function deleteDocument(workspaceId: string, docId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/documents/${docId}`, { method: "DELETE" });
}

// --- Universal Search ---

export async function universalSearch(
  question: string,
  workspaceId?: string,
  resourceTypes?: string[]
): Promise<SearchResponse> {
  const body: Record<string, unknown> = { question };
  if (resourceTypes) body.resource_types = resourceTypes;
  const url = workspaceId
    ? `/api/v1/workspaces/${workspaceId}/search`
    : `/api/v1/me/search`;
  return apiFetch<SearchResponse>(url, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- Wiki: Backlinks, Page Graph, Semantic Search ---

export async function getBacklinks(
  workspaceId: string,
  notebookId: string,
  pageId: string
): Promise<PageLink[]> {
  const data = await apiFetch<{ backlinks: PageLink[] }>(
    `/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/pages/${pageId}/backlinks`
  );
  return data.backlinks;
}

export async function getPersonalBacklinks(
  notebookId: string,
  pageId: string
): Promise<PageLink[]> {
  const data = await apiFetch<{ backlinks: PageLink[] }>(
    `/api/v1/notebooks/${notebookId}/pages/${pageId}/backlinks`
  );
  return data.backlinks;
}

export async function getOutlinks(
  workspaceId: string,
  notebookId: string,
  pageId: string
): Promise<PageLink[]> {
  const data = await apiFetch<{ outlinks: PageLink[] }>(
    `/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/pages/${pageId}/outlinks`
  );
  return data.outlinks;
}

export async function getPageGraph(
  workspaceId: string,
  notebookId: string
): Promise<PageGraph> {
  return apiFetch<PageGraph>(
    `/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/graph`
  );
}

export async function getPersonalOutlinks(
  notebookId: string,
  pageId: string
): Promise<PageLink[]> {
  const data = await apiFetch<{ outlinks: PageLink[] }>(
    `/api/v1/notebooks/${notebookId}/pages/${pageId}/outlinks`
  );
  return data.outlinks;
}

export async function getPersonalPageGraph(notebookId: string): Promise<PageGraph> {
  return apiFetch<PageGraph>(`/api/v1/notebooks/${notebookId}/graph`);
}

export async function semanticSearchPersonalPages(
  notebookId: string,
  query: string,
  limit = 20
): Promise<NotebookPage[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const data = await apiFetch<{ pages: NotebookPage[] }>(
    `/api/v1/notebooks/${notebookId}/pages/semantic-search?${params}`
  );
  return data.pages;
}

export async function autoIndexPersonalNotebook(
  notebookId: string
): Promise<NotebookPage> {
  return apiFetch<NotebookPage>(
    `/api/v1/notebooks/${notebookId}/auto-index`,
    { method: "POST" }
  );
}

export async function semanticSearchPages(
  workspaceId: string,
  notebookId: string,
  query: string,
  limit = 20
): Promise<NotebookPage[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const data = await apiFetch<{ pages: NotebookPage[] }>(
    `/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/pages/semantic-search?${params}`
  );
  return data.pages;
}

export async function autoIndexNotebook(
  workspaceId: string,
  notebookId: string
): Promise<NotebookPage> {
  return apiFetch<NotebookPage>(
    `/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/auto-index`,
    { method: "POST" }
  );
}

// --- Table Embeddings ---

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

// --- Sleep Agent Config ---

export async function getSleepConfig(): Promise<SleepConfig> {
  return apiFetch<SleepConfig>("/api/v1/personas/me/sleep/config");
}

export async function updateSleepConfig(
  updates: Partial<SleepConfig>
): Promise<SleepConfig> {
  return apiFetch<SleepConfig>("/api/v1/personas/me/sleep/config", {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export async function getPersonaSleepConfig(personaId: string): Promise<SleepConfig> {
  return apiFetch<SleepConfig>(`/api/v1/personas/${personaId}/sleep/config`);
}

export async function updatePersonaSleepConfig(
  personaId: string,
  updates: Partial<SleepConfig>
): Promise<SleepConfig> {
  return apiFetch<SleepConfig>(`/api/v1/personas/${personaId}/sleep/config`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export async function triggerPersonaSleep(
  personaId: string
): Promise<Record<string, unknown>> {
  return apiFetch(`/api/v1/personas/${personaId}/sleep`, { method: "POST" });
}

export async function triggerSleep(): Promise<Record<string, unknown>> {
  return apiFetch("/api/v1/personas/me/sleep", { method: "POST" });
}
