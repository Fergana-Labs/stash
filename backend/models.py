from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# --- Users ---


class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str | None = Field(None, max_length=128)
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
    joined_at: datetime


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


# --- Tables ---


class ColumnDefinition(BaseModel):
    id: str = Field("", max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(
        ..., pattern=r"^(text|number|boolean|date|datetime|url|email|select|multiselect|json)$",
    )
    order: int = Field(0, ge=0)
    required: bool = False
    default: str | int | float | bool | list | None = None
    options: list[str] | None = None


class TableCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=1000)
    columns: list[ColumnDefinition] = Field(default_factory=list)


class TableUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)


class TableResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    name: str
    description: str
    columns: list[ColumnDefinition]
    created_by: UUID
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime
    row_count: int | None = None


class TableListResponse(BaseModel):
    tables: list[TableResponse]


class ColumnAddRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(
        ..., pattern=r"^(text|number|boolean|date|datetime|url|email|select|multiselect|json)$",
    )
    required: bool = False
    default: str | int | float | bool | list | None = None
    options: list[str] | None = None


class ColumnUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    type: str | None = Field(
        None, pattern=r"^(text|number|boolean|date|datetime|url|email|select|multiselect|json)$",
    )
    required: bool | None = None
    default: str | int | float | bool | list | None = None
    options: list[str] | None = None


class ColumnReorderRequest(BaseModel):
    column_ids: list[str]


class RowCreateRequest(BaseModel):
    data: dict = Field(default_factory=dict)


class RowBatchCreateRequest(BaseModel):
    rows: list[RowCreateRequest] = Field(..., min_length=1, max_length=5000)


class RowUpdateRequest(BaseModel):
    data: dict


class RowBatchUpdateItem(BaseModel):
    row_id: UUID
    data: dict


class RowBatchUpdateRequest(BaseModel):
    rows: list[RowBatchUpdateItem] = Field(..., min_length=1, max_length=5000)


class RowResponse(BaseModel):
    id: UUID
    table_id: UUID
    data: dict
    row_order: int
    created_by: UUID
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime


class RowListResponse(BaseModel):
    rows: list[RowResponse]
    total_count: int
    has_more: bool


# --- History ---


class Attachment(BaseModel):
    file_id: UUID
    name: str
    content_type: str


class HistoryEventCreateRequest(BaseModel):
    agent_name: str = Field(..., min_length=1, max_length=64)
    event_type: str = Field(..., min_length=1, max_length=64)
    content: str = Field(..., min_length=1)
    session_id: str | None = Field(None, max_length=64)
    tool_name: str | None = Field(None, max_length=128)
    metadata: dict = Field(default_factory=dict)
    attachments: list[Attachment] | None = None


class HistoryEventBatchRequest(BaseModel):
    events: list[HistoryEventCreateRequest] = Field(..., min_length=1, max_length=100)


class HistoryEventResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None = None
    created_by: UUID | None = None
    agent_name: str
    event_type: str
    session_id: str | None
    tool_name: str | None
    content: str
    metadata: dict
    attachments: list[dict] | None = None
    created_at: datetime
    workspace_name: str | None = None


class HistoryEventListResponse(BaseModel):
    events: list[HistoryEventResponse]
    has_more: bool


class HistoryQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(20, ge=1, le=100)


class HistoryQueryResponse(BaseModel):
    answer: str
    sources: list[HistoryEventResponse]


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


# --- Files ---


class FileResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    name: str
    content_type: str
    size_bytes: int
    url: str
    uploaded_by: UUID
    created_at: datetime


class FileListResponse(BaseModel):
    files: list[FileResponse]
