export interface User {
  id: string;
  name: string;
  display_name: string | null;
  type: "human" | "agent";
  description: string;
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

export interface Room {
  id: string;
  name: string;
  description: string;
  creator_id: string;
  invite_code: string;
  is_public: boolean;
  type: "chat" | "workspace" | "dm";
  created_at: string;
  member_count: number | null;
}

export interface RoomMember {
  user_id: string;
  name: string;
  display_name: string | null;
  type: "human" | "agent";
  role: string;
  joined_at: string;
}

export interface Message {
  id: string;
  room_id: string;
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
  // Message fields (when type === "message")
  id?: string;
  room_id?: string;
  sender_id?: string;
  sender_name?: string;
  sender_display_name?: string | null;
  sender_type?: string;
  content?: string;
  message_type?: string;
  reply_to_id?: string | null;
  created_at?: string;
}

export interface WorkspaceFile {
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

export interface WorkspaceFolder {
  id: string;
  workspace_id: string;
  name: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface FileTreeFile {
  id: string;
  name: string;
  folder_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface FileTreeFolder {
  id: string;
  name: string;
  files: FileTreeFile[];
  created_at: string;
}

export interface FileTree {
  folders: FileTreeFolder[];
  root_files: FileTreeFile[];
}

export interface DMOtherUser {
  id: string;
  name: string;
  display_name: string | null;
  type: string;
}

export interface DMConversation {
  id: string;
  name: string;
  description: string;
  creator_id: string;
  invite_code: string;
  is_public: boolean;
  type: string;
  created_at: string;
  member_count: number | null;
  other_user: DMOtherUser | null;
  last_message_at: string | null;
}

export interface UserSearchResult {
  id: string;
  name: string;
  display_name: string | null;
  type: string;
}
