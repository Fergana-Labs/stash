import { Message, RegisterResponse, Room, RoomMember, User, WorkspaceFile, WorkspaceFolder, FileTree, DMConversation, UserSearchResult } from "./types";

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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

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

// --- Rooms ---
export async function createRoom(
  name: string,
  description?: string,
  isPublic?: boolean,
  type?: "chat" | "workspace"
): Promise<Room> {
  return apiFetch("/api/v1/rooms", {
    method: "POST",
    body: JSON.stringify({
      name,
      description: description || "",
      is_public: isPublic ?? true,
      type: type || "chat",
    }),
  });
}

export async function listPublicRooms(): Promise<{ rooms: Room[] }> {
  return apiFetch("/api/v1/rooms");
}

export async function listMyRooms(): Promise<{ rooms: Room[] }> {
  return apiFetch("/api/v1/rooms/mine");
}

export async function getRoom(roomId: string): Promise<Room> {
  return apiFetch(`/api/v1/rooms/${roomId}`);
}

export async function joinRoom(inviteCode: string): Promise<Room> {
  return apiFetch(`/api/v1/rooms/join/${inviteCode}`, { method: "POST" });
}

export async function leaveRoom(roomId: string): Promise<void> {
  await apiFetch(`/api/v1/rooms/${roomId}/leave`, { method: "POST" });
}

export async function getRoomMembers(roomId: string): Promise<RoomMember[]> {
  return apiFetch(`/api/v1/rooms/${roomId}/members`);
}

export async function deleteRoom(roomId: string): Promise<void> {
  await apiFetch(`/api/v1/rooms/${roomId}`, { method: "DELETE" });
}

export async function kickMember(
  roomId: string,
  userId: string
): Promise<void> {
  await apiFetch(`/api/v1/rooms/${roomId}/kick/${userId}`, {
    method: "POST",
  });
}

export async function updateRoom(
  roomId: string,
  data: { name?: string; description?: string }
): Promise<Room> {
  return apiFetch(`/api/v1/rooms/${roomId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// --- Messages ---
export async function sendMessage(
  roomId: string,
  content: string,
  replyToId?: string
): Promise<Message> {
  return apiFetch(`/api/v1/rooms/${roomId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content, reply_to_id: replyToId || null }),
  });
}

export async function getMessages(
  roomId: string,
  params?: { after?: string; before?: string; limit?: number }
): Promise<{ messages: Message[]; has_more: boolean }> {
  const searchParams = new URLSearchParams();
  if (params?.after) searchParams.set("after", params.after);
  if (params?.before) searchParams.set("before", params.before);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return apiFetch(`/api/v1/rooms/${roomId}/messages${qs ? `?${qs}` : ""}`);
}

export async function searchMessages(
  roomId: string,
  query: string,
  limit?: number
): Promise<{ messages: Message[]; has_more: boolean }> {
  const searchParams = new URLSearchParams({ q: query });
  if (limit) searchParams.set("limit", String(limit));
  return apiFetch(
    `/api/v1/rooms/${roomId}/messages/search?${searchParams.toString()}`
  );
}

// --- Access Lists ---
export async function addToAccessList(
  roomId: string,
  userName: string,
  listType: "allow" | "block"
): Promise<{ added: boolean }> {
  return apiFetch(`/api/v1/rooms/${roomId}/access-list`, {
    method: "POST",
    body: JSON.stringify({ user_name: userName, list_type: listType }),
  });
}

export async function removeFromAccessList(
  roomId: string,
  userName: string,
  listType: "allow" | "block"
): Promise<void> {
  await apiFetch(`/api/v1/rooms/${roomId}/access-list`, {
    method: "DELETE",
    body: JSON.stringify({ user_name: userName, list_type: listType }),
  });
}

export interface AccessListEntry {
  user_name: string;
  created_at: string;
}

export async function getAccessList(
  roomId: string,
  listType: "allow" | "block"
): Promise<{ entries: AccessListEntry[] }> {
  return apiFetch(`/api/v1/rooms/${roomId}/access-list/${listType}`);
}

// --- Workspaces ---
export async function listWorkspaceFiles(
  workspaceId: string
): Promise<FileTree> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/files`);
}

export async function createWorkspaceFile(
  workspaceId: string,
  name: string,
  folderId?: string,
  content?: string
): Promise<WorkspaceFile> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/files`, {
    method: "POST",
    body: JSON.stringify({
      name,
      folder_id: folderId || null,
      content: content || "",
    }),
  });
}

export async function getWorkspaceFile(
  workspaceId: string,
  fileId: string
): Promise<WorkspaceFile> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}`);
}

export async function updateWorkspaceFile(
  workspaceId: string,
  fileId: string,
  data: { name?: string; folder_id?: string; content?: string; move_to_root?: boolean }
): Promise<WorkspaceFile> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteWorkspaceFile(
  workspaceId: string,
  fileId: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/files/${fileId}`, {
    method: "DELETE",
  });
}

export async function createWorkspaceFolder(
  workspaceId: string,
  name: string
): Promise<WorkspaceFolder> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/folders`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renameWorkspaceFolder(
  workspaceId: string,
  folderId: string,
  name: string
): Promise<WorkspaceFolder> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/folders/${folderId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

// --- Direct Messages ---
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
  return apiFetch(`/api/v1/users/search?q=${encodeURIComponent(query)}`);
}

export async function deleteWorkspaceFolder(
  workspaceId: string,
  folderId: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/folders/${folderId}`, {
    method: "DELETE",
  });
}
