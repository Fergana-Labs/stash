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
    api_key: str


class UserProfile(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    type: str
    description: str
    owner_id: UUID | None = None
    created_at: datetime
    last_seen: datetime


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(None, max_length=128)
    description: str | None = Field(None, max_length=500)
    password: str | None = Field(None, min_length=8, max_length=128)


class LoginRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserSearchResult(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    type: str


# --- Agent Identities ---


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str | None = Field(None, max_length=128)
    description: str = Field("", max_length=500)


class AgentUpdateRequest(BaseModel):
    display_name: str | None = Field(None, max_length=128)
    description: str | None = Field(None, max_length=500)


class AgentResponse(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    type: str
    description: str
    api_key: str
    owner_id: UUID
    notebook_id: UUID | None = None
    history_id: UUID | None = None
    created_at: datetime


class AgentProfile(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    type: str
    description: str
    owner_id: UUID
    notebook_id: UUID | None = None
    history_id: UUID | None = None
    created_at: datetime
    last_seen: datetime


# --- Agent Resources (notebook/history owned by agent) ---


class AgentPageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    content: str = ""
    metadata: dict = Field(default_factory=dict)


class AgentPageUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    content: str | None = None
    metadata: dict | None = None


class SyncManifestEntry(BaseModel):
    id: UUID
    name: str
    content_hash: str | None
    metadata: dict
    updated_at: datetime


class SyncManifestResponse(BaseModel):
    notebook_id: UUID
    pages: list[SyncManifestEntry]


# --- Workspaces ---


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=1000)
    is_public: bool = False


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=1000)


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: str
    creator_id: UUID
    invite_code: str
    is_public: bool
    created_at: datetime
    updated_at: datetime
    member_count: int | None = None


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceResponse]


class WorkspaceMember(BaseModel):
    user_id: UUID
    name: str
    display_name: str | None
    type: str
    role: str
    notebook_id: UUID | None = None
    history_id: UUID | None = None
    joined_at: datetime


# --- Chats ---


class ChatCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=1000)


class ChatResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    name: str
    description: str
    creator_id: UUID
    is_dm: bool
    created_at: datetime
    updated_at: datetime


class ChatListResponse(BaseModel):
    chats: list[ChatResponse]


class ChatMessageSendRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=16000)
    reply_to_id: UUID | None = None


class ChatMessageResponse(BaseModel):
    id: UUID
    chat_id: UUID
    sender_id: UUID
    sender_name: str
    sender_display_name: str | None
    sender_type: str
    content: str
    message_type: str
    reply_to_id: UUID | None
    created_at: datetime


class ChatMessageListResponse(BaseModel):
    messages: list[ChatMessageResponse]
    has_more: bool


# --- DMs ---


class DMCreateRequest(BaseModel):
    user_id: UUID | None = None
    username: str | None = None


class DMOtherUser(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    type: str


class DMResponse(BaseModel):
    id: UUID
    other_user: DMOtherUser | None = None
    last_message_at: str | None = None
    created_at: datetime


class DMListResponse(BaseModel):
    dms: list[DMResponse]


# --- Notebooks (collections) ---


class NotebookCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=1000)


class NotebookResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    name: str
    description: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class NotebookListResponse(BaseModel):
    notebooks: list[NotebookResponse]


# --- Notebook Pages (files within a notebook) ---


class PageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    folder_id: UUID | None = None
    content: str = ""


class PageUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    folder_id: UUID | None = None
    content: str | None = None
    move_to_root: bool = False


class PageResponse(BaseModel):
    id: UUID
    notebook_id: UUID
    folder_id: UUID | None
    name: str
    content_markdown: str
    content_hash: str | None = None
    metadata: dict = {}
    created_by: UUID
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime


class FolderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class FolderUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class FolderResponse(BaseModel):
    id: UUID
    notebook_id: UUID
    name: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class PageTreeFile(BaseModel):
    id: UUID
    name: str
    folder_id: UUID | None
    created_at: datetime
    updated_at: datetime


class PageTreeFolder(BaseModel):
    id: UUID
    name: str
    files: list[PageTreeFile]
    created_at: datetime


class PageTreeResponse(BaseModel):
    folders: list[PageTreeFolder]
    root_files: list[PageTreeFile]


# --- Decks ---


class DeckCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=1000)
    html_content: str = ""
    deck_type: str = Field("freeform", pattern=r"^(freeform|slides|dashboard)$")


class DeckUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    html_content: str | None = None


class DeckResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    name: str
    description: str
    html_content: str
    deck_type: str
    created_by: UUID
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime


class DeckListResponse(BaseModel):
    decks: list[DeckResponse]


class DeckShareCreateRequest(BaseModel):
    name: str | None = Field(None, max_length=255)
    require_email: bool = False
    passcode: str | None = Field(None, max_length=128)
    allow_download: bool = True
    expires_at: str | None = None


class DeckShareResponse(BaseModel):
    id: UUID
    deck_id: UUID
    token: str
    name: str | None
    is_active: bool
    require_email: bool
    has_passcode: bool
    allow_download: bool
    expires_at: datetime | None
    created_at: datetime


class DeckShareUpdateRequest(BaseModel):
    name: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    require_email: bool | None = None
    passcode: str | None = Field(None, max_length=128)
    clear_passcode: bool = False
    allow_download: bool | None = None
    expires_at: str | None = None
    clear_expires: bool = False


class DeckShareListResponse(BaseModel):
    shares: list[DeckShareResponse]


class DeckShareViewResponse(BaseModel):
    id: UUID
    viewer_email: str | None
    viewer_ip: str | None
    started_at: datetime
    last_active_at: datetime
    total_duration_seconds: int
    view_count: int = 1


class DeckShareAnalyticsResponse(BaseModel):
    total_views: int
    unique_viewers: int
    avg_duration_seconds: int
    viewers: list[DeckShareViewResponse]
    page_stats: list[dict]


# --- History ---


class HistoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=1000)


class HistoryResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    name: str
    description: str
    created_by: UUID
    created_at: datetime
    event_count: int | None = None


class HistoryListResponse(BaseModel):
    stores: list[HistoryResponse]


class HistoryEventCreateRequest(BaseModel):
    agent_name: str = Field(..., min_length=1, max_length=64)
    event_type: str = Field(..., min_length=1, max_length=64)
    content: str = Field(..., min_length=1)
    session_id: str | None = Field(None, max_length=64)
    tool_name: str | None = Field(None, max_length=128)
    metadata: dict = Field(default_factory=dict)


class HistoryEventBatchRequest(BaseModel):
    events: list[HistoryEventCreateRequest] = Field(..., min_length=1, max_length=100)


class HistoryEventResponse(BaseModel):
    id: UUID
    store_id: UUID
    agent_name: str
    event_type: str
    session_id: str | None
    tool_name: str | None
    content: str
    metadata: dict
    created_at: datetime


class HistoryEventListResponse(BaseModel):
    events: list[HistoryEventResponse]
    has_more: bool


# --- Object Permissions ---


class PermissionResponse(BaseModel):
    object_type: str
    object_id: UUID
    visibility: str  # inherit, private, public
    shares: list["ShareResponse"] = []


class SetVisibilityRequest(BaseModel):
    visibility: str = Field(..., pattern=r"^(inherit|private|public)$")


class ShareRequest(BaseModel):
    user_id: UUID
    permission: str = Field("read", pattern=r"^(read|write|admin)$")


class ShareResponse(BaseModel):
    user_id: UUID
    user_name: str
    permission: str
    granted_by: UUID
    created_at: datetime


# --- Webhooks ---


class WebhookCreateRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    secret: str | None = Field(None, max_length=128)
    event_filter: list[str] = Field(default_factory=list)


class WebhookUpdateRequest(BaseModel):
    url: str | None = Field(None, min_length=1, max_length=2048)
    secret: str | None = Field(None, max_length=128)
    event_filter: list[str] | None = None
    is_active: bool | None = None


class WebhookResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    url: str
    has_secret: bool
    event_filter: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Chat Watches ---


class WatchResponse(BaseModel):
    agent_id: UUID
    chat_id: UUID
    workspace_id: UUID | None = None
    chat_name: str = ""
    workspace_name: str = ""
    last_read_at: datetime
    enabled: bool = True
    created_at: datetime


class WatchListResponse(BaseModel):
    watches: list[WatchResponse]


class UnreadChatResponse(BaseModel):
    chat_id: UUID
    chat_name: str
    workspace_id: UUID | None = None
    workspace_name: str = ""
    unread_count: int
    last_read_at: datetime
    latest_message_at: datetime | None = None


class UnreadListResponse(BaseModel):
    unread: list[UnreadChatResponse]
    total_unread: int


# --- Injection ---


class SessionItemState(BaseModel):
    last_injected_prompt: int = 0
    last_injected_ts: str = ""
    token_cost: int = 0


class SessionInjectionState(BaseModel):
    prompt_num: int = 0
    session_start: str = ""
    items: dict[str, SessionItemState] = Field(default_factory=dict)


class InjectionRequest(BaseModel):
    prompt_text: str = Field(..., min_length=1, max_length=32000)
    session_id: str | None = Field(None, max_length=64)
    session_state: SessionInjectionState = Field(default_factory=SessionInjectionState)


class InjectedItem(BaseModel):
    key: str
    source_type: str
    score: float
    token_cost: int


class InjectionResponse(BaseModel):
    context: str
    updated_session_state: SessionInjectionState
    injected_items: list[InjectedItem]
    total_tokens_used: int
    budget_tokens: int


# --- WebSocket ---


class WSMessage(BaseModel):
    type: str = "message"  # "message" | "typing" | "system"
    content: str | None = None
    reply_to_id: UUID | None = None
