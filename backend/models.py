from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# --- Users ---
class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str | None = Field(None, max_length=128)
    type: str = Field("human", pattern=r"^(human|agent)$")
    description: str = Field("", max_length=500)


class UserRegisterResponse(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    type: str
    api_key: str  # Only shown once


class UserProfile(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    type: str
    description: str
    created_at: datetime
    last_seen: datetime


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(None, max_length=128)
    description: str | None = Field(None, max_length=500)


# --- Rooms ---
class RoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=1000)
    is_public: bool = True


class RoomResponse(BaseModel):
    id: UUID
    name: str
    description: str
    creator_id: UUID
    invite_code: str
    is_public: bool
    created_at: datetime
    member_count: int | None = None


class RoomListResponse(BaseModel):
    rooms: list[RoomResponse]


class RoomMember(BaseModel):
    user_id: UUID
    name: str
    display_name: str | None
    type: str
    role: str
    joined_at: datetime


class RoomUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=1000)


class AccessListRequest(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=64)
    list_type: str = Field(..., pattern=r"^(allow|block)$")


# --- Messages ---
class MessageSendRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    reply_to_id: UUID | None = None


class MessageResponse(BaseModel):
    id: UUID
    room_id: UUID
    sender_id: UUID
    sender_name: str
    sender_display_name: str | None
    sender_type: str
    content: str
    message_type: str
    reply_to_id: UUID | None
    created_at: datetime


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    has_more: bool


# --- WebSocket ---
class WSMessage(BaseModel):
    type: str = "message"  # "message" | "typing" | "system"
    content: str | None = None
    reply_to_id: UUID | None = None
