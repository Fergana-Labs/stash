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
