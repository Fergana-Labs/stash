from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# --- Users ---
class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str | None = Field(None, max_length=128)
    type: str = Field("human", pattern=r"^(human|agent)$")
    description: str = Field("", max_length=500)
    password: str | None = Field(None, min_length=8, max_length=128)


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
    password: str | None = Field(None, min_length=8, max_length=128)


class LoginRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


# --- Rooms ---
class RoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=1000)
    is_public: bool = True
    type: str = Field("chat", pattern=r"^(chat|workspace)$")


class RoomResponse(BaseModel):
    id: UUID
    name: str
    description: str
    creator_id: UUID
    invite_code: str
    is_public: bool
    type: str = "chat"
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
    content: str = Field(..., min_length=1, max_length=16000)
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


# --- Webhooks ---
class WebhookCreateRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    secret: str | None = Field(None, max_length=128)


class WebhookUpdateRequest(BaseModel):
    url: str | None = Field(None, min_length=1, max_length=2048)
    secret: str | None = Field(None, max_length=128)
    is_active: bool | None = None


class WebhookResponse(BaseModel):
    id: UUID
    user_id: UUID
    url: str
    has_secret: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- WebSocket ---
class WSMessage(BaseModel):
    type: str = "message"  # "message" | "typing" | "system"
    content: str | None = None
    reply_to_id: UUID | None = None


# --- Workspace Files & Folders ---
class WorkspaceFileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    folder_id: UUID | None = None
    content: str = ""


class WorkspaceFileUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    folder_id: UUID | None = None
    content: str | None = None
    move_to_root: bool = False  # Set True to move file out of a folder to root


class WorkspaceFileResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    folder_id: UUID | None
    name: str
    content_markdown: str
    created_by: UUID
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime


class WorkspaceFolderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class WorkspaceFolderUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class WorkspaceFolderResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class WorkspaceFileTreeFile(BaseModel):
    id: UUID
    name: str
    folder_id: UUID | None
    created_at: datetime
    updated_at: datetime


class WorkspaceFileTreeFolder(BaseModel):
    id: UUID
    name: str
    files: list[WorkspaceFileTreeFile]
    created_at: datetime


class WorkspaceFileTreeResponse(BaseModel):
    folders: list[WorkspaceFileTreeFolder]
    root_files: list[WorkspaceFileTreeFile]
