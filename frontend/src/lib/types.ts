export interface User {
  id: string;
  name: string;
  display_name: string | null;
  type: "human" | "agent";
  description: string;
  owner_id: string | null;
  created_at: string;
  last_seen: string;
}

export interface RegisterResponse {
  id: string;
  name: string;
  display_name: string | null;
  type: string;
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
  type: "human" | "agent";
  role: string;
  joined_at: string;
}

// --- Chats ---

export interface Chat {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string;
  creator_id: string;
  is_dm: boolean;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  chat_id: string;
  sender_id: string;
  sender_name: string;
  sender_display_name: string | null;
  sender_type: "human" | "agent";
  content: string;
  message_type: "text" | "system";
  reply_to_id: string | null;
  created_at: string;
}

export interface WSEvent {
  type: "message" | "typing" | "system";
  user?: string;
  id?: string;
  chat_id?: string;
  sender_id?: string;
  sender_name?: string;
  sender_display_name?: string | null;
  sender_type?: string;
  content?: string;
  message_type?: string;
  reply_to_id?: string | null;
  created_at?: string;
}

// --- Notebooks ---

export interface Notebook {
  id: string;
  workspace_id: string;
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
  workspace_id: string;
  name: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface NotebookTreeFile {
  id: string;
  name: string;
  folder_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotebookTreeFolder {
  id: string;
  name: string;
  files: NotebookTreeFile[];
  created_at: string;
}

export interface NotebookTree {
  folders: NotebookTreeFolder[];
  root_files: NotebookTreeFile[];
}

// --- Memory Stores ---

export interface MemoryStore {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
  event_count: number | null;
}

export interface MemoryEvent {
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

// --- DMs ---

export interface DMOtherUser {
  id: string;
  name: string;
  display_name: string | null;
  type: string;
}

export interface DMConversation {
  id: string;
  other_user: DMOtherUser | null;
  last_message_at: string | null;
  created_at: string;
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

// --- Search ---

export interface UserSearchResult {
  id: string;
  name: string;
  display_name: string | null;
  type: string;
}
