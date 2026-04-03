export interface User {
  id: string;
  name: string;
  display_name: string | null;
  type: "human" | "persona";
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
  type: "human" | "persona";
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
  sender_type: "human" | "persona";
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

// --- Notebooks (collections) ---

export interface Notebook {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

// --- Notebook Pages (files within a notebook) ---

export interface NotebookPage {
  id: string;
  notebook_id: string;
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
  notebook_id: string;
  name: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PageTreeFile {
  id: string;
  name: string;
  folder_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PageTreeFolder {
  id: string;
  name: string;
  files: PageTreeFile[];
  created_at: string;
}

export interface PageTree {
  folders: PageTreeFolder[];
  root_files: PageTreeFile[];
}

// --- History ---

export interface History {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
  event_count: number | null;
}

export interface HistoryEvent {
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

// --- Personas ---

export interface PersonaProfile {
  id: string;
  name: string;
  display_name: string | null;
  type: string;
  description: string;
  owner_id: string;
  created_at: string;
  last_seen: string;
}

export interface PersonaResponse {
  id: string;
  name: string;
  display_name: string | null;
  type: string;
  description: string;
  api_key: string;
  owner_id: string;
  created_at: string;
}

// --- Decks ---

export interface Deck {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string;
  html_content: string;
  deck_type: string;
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeckShare {
  id: string;
  deck_id: string;
  token: string;
  name: string | null;
  is_active: boolean;
  require_email: boolean;
  has_passcode: boolean;
  allow_download: boolean;
  expires_at: string | null;
  created_at: string;
}

export interface DeckWithWorkspace {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string;
  deck_type: string;
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  workspace_name: string | null;
}

// --- Tables ---

export interface TableColumn {
  id: string;
  name: string;
  type: "text" | "number" | "boolean" | "date" | "datetime" | "url" | "email" | "select" | "multiselect" | "json";
  order: number;
  required: boolean;
  default: string | number | boolean | string[] | null;
  options: string[] | null;
}

export interface Table {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string;
  columns: TableColumn[];
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  row_count: number | null;
}

export interface TableRow {
  id: string;
  table_id: string;
  data: Record<string, unknown>;
  row_order: number;
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface TableWithWorkspace extends Table {
  workspace_name: string | null;
}

// --- Aggregate ---

export interface ChatWithWorkspace extends Chat {
  workspace_name?: string;
}

export interface DMWithUser {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string;
  creator_id: string;
  is_dm: boolean;
  created_at: string;
  updated_at: string;
  other_user: DMOtherUser | null;
}

export interface NotebookWithWorkspace extends Notebook {
  workspace_name: string | null;
}

export interface HistoryWithWorkspace extends History {
  workspace_name: string | null;
}

export interface HistoryEventWithContext extends HistoryEvent {
  store_name: string;
  workspace_id: string | null;
  workspace_name: string | null;
}

export interface Webhook {
  id: string;
  workspace_id: string;
  user_id: string;
  url: string;
  has_secret: boolean;
  event_filter: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PersonaWithContext extends PersonaProfile {
  workspaces: { workspace_id: string; workspace_name: string; role: string }[];
}

// --- Search ---

export interface UserSearchResult {
  id: string;
  name: string;
  display_name: string | null;
  type: string;
}
