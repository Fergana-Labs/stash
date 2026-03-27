import {
  Chat,
  DMConversation,
  MemoryEvent,
  MemoryStore,
  Message,
  Notebook,
  NotebookFolder,
  NotebookTree,
  ObjectPermission,
  RegisterResponse,
  User,
  UserSearchResult,
  Workspace,
  WorkspaceMember,
} from "./types";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("moltchat_token");
}

export function setToken(token: string) {
  localStorage.setItem("moltchat_token", token);
}

export function clearToken() {
  localStorage.removeItem("moltchat_token");
}

const API_BASE = "";

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
  type: "human" | "agent",
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

// --- Notebooks ---

export async function listNotebooks(workspaceId: string): Promise<NotebookTree> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks`);
}

export async function createNotebook(
  workspaceId: string,
  name: string,
  folderId?: string,
  content?: string
): Promise<Notebook> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks`, {
    method: "POST",
    body: JSON.stringify({
      name,
      folder_id: folderId || null,
      content: content || "",
    }),
  });
}

export async function getNotebook(workspaceId: string, notebookId: string): Promise<Notebook> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}`);
}

export async function updateNotebook(
  workspaceId: string,
  notebookId: string,
  data: { name?: string; folder_id?: string; content?: string; move_to_root?: boolean }
): Promise<Notebook> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteNotebook(workspaceId: string, notebookId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}`, { method: "DELETE" });
}

export async function createNotebookFolder(workspaceId: string, name: string): Promise<NotebookFolder> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/folders`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renameNotebookFolder(
  workspaceId: string,
  folderId: string,
  name: string
): Promise<NotebookFolder> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/folders/${folderId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteNotebookFolder(workspaceId: string, folderId: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/notebooks/folders/${folderId}`, { method: "DELETE" });
}

// --- Memory Stores ---

export async function createMemoryStore(
  workspaceId: string,
  name: string,
  description?: string
): Promise<MemoryStore> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/memory`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
}

export async function listMemoryStores(workspaceId: string): Promise<{ stores: MemoryStore[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/memory`);
}

export async function getMemoryStore(workspaceId: string, storeId: string): Promise<MemoryStore> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/memory/${storeId}`);
}

export async function queryMemoryEvents(
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
): Promise<{ events: MemoryEvent[]; has_more: boolean }> {
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

export async function searchMemoryEvents(
  workspaceId: string,
  storeId: string,
  query: string,
  limit?: number
): Promise<{ events: MemoryEvent[]; has_more: boolean }> {
  const searchParams = new URLSearchParams({ q: query });
  if (limit) searchParams.set("limit", String(limit));
  return apiFetch(
    `/api/v1/workspaces/${workspaceId}/memory/${storeId}/events/search?${searchParams.toString()}`
  );
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
