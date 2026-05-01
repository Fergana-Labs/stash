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
    api_key: str


class UserProfile(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    description: str
    created_at: datetime
    last_seen: datetime


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(None, max_length=128)
    description: str | None = Field(None, max_length=500)
    password: str | None = Field(None, min_length=8, max_length=128)
    # Required whenever `password` is set — stops a stolen session key from
    # being enough to permanently take over the account.
    current_password: str | None = Field(None, max_length=128)


class LoginRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserSearchResult(BaseModel):
    id: UUID
    name: str
    display_name: str | None


class ApiKeyInfo(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field("Personal token", min_length=1, max_length=128)


class ApiKeyCreateResponse(BaseModel):
    id: UUID
    name: str
    api_key: str  # raw token — shown exactly once
    created_at: datetime


# --- Workspaces ---


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=1000)
    is_public: bool = False


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=1000)
    summary: str | None = Field(None, max_length=280)
    tags: list[str] | None = None
    category: str | None = Field(None, max_length=32)
    cover_image_url: str | None = None
    is_public: bool | None = None


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
    summary: str | None = None
    tags: list[str] = []
    category: str | None = None
    featured: bool = False
    cover_image_url: str | None = None
    fork_count: int = 0
    forked_from_workspace_id: UUID | None = None


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceResponse]


class WorkspaceForkRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)


# --- Discover catalog ---


class WorkspaceCatalogCard(BaseModel):
    id: UUID
    name: str
    summary: str | None = None
    description: str
    is_public: bool
    tags: list[str] = []
    category: str | None = None
    featured: bool = False
    cover_image_url: str | None = None
    creator_id: UUID
    creator_name: str
    creator_display_name: str | None = None
    member_count: int = 0
    fork_count: int = 0
    notebook_count: int = 0
    table_count: int = 0
    file_count: int = 0
    history_event_count: int = 0
    forked_from_workspace_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class CatalogListResponse(BaseModel):
    workspaces: list[WorkspaceCatalogCard]
    next_cursor: str | None = None


class WorkspacePublicNotebookSummary(BaseModel):
    id: UUID
    name: str
    description: str
    page_count: int
    updated_at: datetime


class WorkspacePublicTableSummary(BaseModel):
    id: UUID
    name: str
    row_count: int
    updated_at: datetime


class WorkspacePublicFileSummary(BaseModel):
    id: UUID
    name: str
    size_bytes: int
    created_at: datetime


class WorkspacePublicDetail(BaseModel):
    workspace: WorkspaceCatalogCard
    notebooks: list[WorkspacePublicNotebookSummary]
    tables: list[WorkspacePublicTableSummary]
    files: list[WorkspacePublicFileSummary]


# --- Views (curated subsets of a workspace) ---

ViewObjectType = str  # 'notebook' | 'table' | 'file' | 'history'


class ViewItem(BaseModel):
    object_type: ViewObjectType = Field(..., pattern=r"^(notebook|table|file|history)$")
    object_id: UUID
    position: int = 0
    label_override: str | None = Field(None, max_length=160)


class ViewCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: str = Field("", max_length=2000)
    is_public: bool = False
    cover_image_url: str | None = None
    items: list[ViewItem] = Field(default_factory=list)


class ViewUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=160)
    description: str | None = Field(None, max_length=2000)
    is_public: bool | None = None
    cover_image_url: str | None = None
    items: list[ViewItem] | None = None


class ViewResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    slug: str
    title: str
    description: str
    owner_id: UUID
    is_public: bool
    cover_image_url: str | None = None
    view_count: int
    items: list[ViewItem]
    created_at: datetime
    updated_at: datetime


class ViewListResponse(BaseModel):
    views: list[ViewResponse]


# Public renderer payload — items are inlined with their content where it
# makes sense (notebook pages, table rows, file metadata, history events).
# The shape is intentionally permissive: each entry has the item
# type/id/label plus an `inline` blob whose contents depend on the type.


class ViewItemInlined(BaseModel):
    object_type: ViewObjectType
    object_id: UUID
    position: int
    label: str
    inline: dict


class ViewPublicResponse(BaseModel):
    view: ViewResponse
    workspace_name: str
    workspace_is_public: bool
    items: list[ViewItemInlined]


class ViewForkRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)


class WorkspaceMember(BaseModel):
    user_id: UUID
    name: str
    display_name: str | None
    role: str
    joined_at: datetime


# --- Invite tokens (magic-link onboarding) ---


class InviteTokenCreateRequest(BaseModel):
    max_uses: int = Field(1, ge=1, le=1000)
    ttl_days: int = Field(7, ge=1, le=90)


class InviteTokenCreateResponse(BaseModel):
    id: UUID
    token: str
    workspace_id: UUID
    workspace_name: str
    max_uses: int
    expires_at: datetime


class InviteTokenSummary(BaseModel):
    id: UUID
    workspace_id: UUID
    max_uses: int
    uses_count: int
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None


class InviteTokenListResponse(BaseModel):
    tokens: list[InviteTokenSummary]


class RedeemInviteRequest(BaseModel):
    """Unauthenticated redemption: creates a fresh user + joins the workspace."""

    token: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=128)


class RedeemInviteResponse(BaseModel):
    api_key: str
    user_id: UUID
    username: str
    display_name: str | None
    workspace_id: UUID
    workspace_name: str


class RedeemInviteAuthedRequest(BaseModel):
    """Authenticated redemption: just joins the existing user to the workspace."""

    token: str = Field(..., min_length=8, max_length=128)


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
    content_type: str = Field("markdown", pattern=r"^(markdown|html)$")
    content_html: str = ""


class PageUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    folder_id: UUID | None = None
    content: str | None = None
    content_type: str | None = Field(None, pattern=r"^(markdown|html)$")
    content_html: str | None = None
    move_to_root: bool = False


class PageResponse(BaseModel):
    id: UUID
    notebook_id: UUID
    folder_id: UUID | None
    name: str
    content_markdown: str
    content_type: str = "markdown"
    content_html: str = ""
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


class WorkspacePageEntry(BaseModel):
    """Flattened reference to a page for cross-notebook lookups (wiki links).

    folder_name is the text used in path-style links like
    `[[folder/page]]`; null when the page lives at the notebook root.
    """

    id: UUID
    name: str
    notebook_id: UUID
    notebook_name: str
    folder_id: UUID | None = None
    folder_name: str | None = None
    updated_at: datetime


class WorkspacePageListResponse(BaseModel):
    pages: list[WorkspacePageEntry]


# --- Tables ---


class ColumnDefinition(BaseModel):
    id: str = Field("", max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(
        ...,
        pattern=r"^(text|number|boolean|date|datetime|url|email|select|multiselect|json)$",
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
        ...,
        pattern=r"^(text|number|boolean|date|datetime|url|email|select|multiselect|json)$",
    )
    required: bool = False
    default: str | int | float | bool | list | None = None
    options: list[str] | None = None


class ColumnUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    type: str | None = Field(
        None,
        pattern=r"^(text|number|boolean|date|datetime|url|email|select|multiselect|json)$",
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
    tag_name: str = Field(..., min_length=1, max_length=64)
    event_type: str = Field(..., min_length=1, max_length=64)
    content: str = Field(..., min_length=1)
    session_id: str | None = Field(None, max_length=64)
    tool_name: str | None = Field(None, max_length=128)
    metadata: dict = Field(default_factory=dict)
    attachments: list[Attachment] | None = None
    created_at: datetime | None = Field(
        None, description="ISO timestamp; defaults to now if omitted"
    )


class HistoryEventBatchRequest(BaseModel):
    events: list[HistoryEventCreateRequest] = Field(..., min_length=1, max_length=100)


class HistoryEventResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None = None
    created_by: UUID | None = None
    created_by_name: str | None = None
    tag_name: str
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


class SessionTranscriptResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    session_id: str
    tag_name: str
    size_bytes: int
    cwd: str | None
    download_url: str | None
    uploaded_by: UUID
    uploaded_at: datetime


# --- Join Requests ---


class JoinRequestResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: UUID | None = None
    user_name: str | None = None
    user_display_name: str | None = None


class JoinRequestListResponse(BaseModel):
    requests: list[JoinRequestResponse]


class WorkspacePublicInfo(BaseModel):
    id: UUID
    name: str
    member_count: int
