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
    discoverable: bool = False
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
    discoverable: bool = False
    featured: bool = False
    cover_image_url: str | None = None
    creator_id: UUID
    creator_name: str
    creator_display_name: str | None = None
    member_count: int = 0
    fork_count: int = 0
    page_count: int = 0
    table_count: int = 0
    file_count: int = 0
    history_event_count: int = 0
    forked_from_workspace_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class CatalogListResponse(BaseModel):
    workspaces: list[WorkspaceCatalogCard]
    next_cursor: str | None = None


class WorkspacePublicFolderSummary(BaseModel):
    id: UUID
    name: str
    parent_folder_id: UUID | None = None
    page_count: int
    updated_at: datetime


class WorkspacePublicRootPageSummary(BaseModel):
    id: UUID
    name: str
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
    folders: list[WorkspacePublicFolderSummary]
    root_pages: list[WorkspacePublicRootPageSummary]
    tables: list[WorkspacePublicTableSummary]
    files: list[WorkspacePublicFileSummary]


class DiscoverCatalogUpdateRequest(BaseModel):
    discoverable: bool | None = None
    featured: bool | None = None
    summary: str | None = Field(None, max_length=280)
    tags: list[str] | None = None
    category: str | None = Field(None, max_length=32)
    cover_image_url: str | None = None


# --- Views (curated subsets of a workspace) ---

ViewObjectType = str  # 'folder' | 'page' | 'table' | 'file' | 'history'


class ViewItem(BaseModel):
    object_type: ViewObjectType = Field(..., pattern=r"^(folder|page|table|file|history)$")
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
# makes sense (folders/pages, table rows, file metadata, history events).
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


# --- Wiki: folders (nested) and pages ---


class FolderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_folder_id: UUID | None = None


class FolderUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    parent_folder_id: UUID | None = None
    move_to_root: bool = False


class FolderResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    parent_folder_id: UUID | None = None
    name: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class FolderListResponse(BaseModel):
    folders: list[FolderResponse]


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
    workspace_id: UUID
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


class PageSummary(BaseModel):
    """Lightweight page entry used in workspace tree responses."""

    id: UUID
    name: str
    workspace_id: UUID
    folder_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class WorkspaceTreeFolder(BaseModel):
    id: UUID
    workspace_id: UUID
    parent_folder_id: UUID | None
    name: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    folders: list["WorkspaceTreeFolder"] = []
    pages: list[PageSummary] = []


class WorkspaceTreeResponse(BaseModel):
    folders: list[WorkspaceTreeFolder]
    pages: list[PageSummary]


class WorkspacePageEntry(BaseModel):
    """Flat reference to a page for wiki-link lookups.

    folder_path is the chain of folder names from the workspace root down to
    the immediate parent — empty for root pages, ['Architecture', 'API'] for
    a page nested two folders deep. Used to render and resolve
    `[[folder/page]]` wiki links.
    """

    id: UUID
    name: str
    workspace_id: UUID
    folder_id: UUID | None = None
    folder_path: list[str] = []
    updated_at: datetime


class WorkspacePageListResponse(BaseModel):
    pages: list[WorkspacePageEntry]


class UserPageEntry(WorkspacePageEntry):
    """Cross-workspace flat page list used by /me/pages."""

    workspace_name: str


class UserPageListResponse(BaseModel):
    pages: list[UserPageEntry]


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
    agent_name: str = Field(..., min_length=1, max_length=64)
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
    visibility: str  # inherit, private, link, public
    shares: list["ShareResponse"] = []


class SetVisibilityRequest(BaseModel):
    visibility: str = Field(..., pattern=r"^(inherit|private|link|public)$")


class ShareRequest(BaseModel):
    user_id: UUID
    permission: str = Field("read", pattern=r"^(read|write|admin)$")


class ShareResponse(BaseModel):
    user_id: UUID
    user_name: str
    permission: str
    granted_by: UUID
    created_at: datetime


class ShareLinkResponse(BaseModel):
    """URL the share sheet copies to clipboard. For workspaces this points at
    /s/{slug-or-uuid}; for everything else it points at the auto-created
    one-item View at /v/{slug}."""

    url: str
    kind: str  # 'workspace' | 'view'
    view_id: UUID | None = None
    view_slug: str | None = None


class PublishRequest(BaseModel):
    """Single-call publish: create a page from supplied content and return a
    share URL for it. Designed for AI agents — collapses 4-5 round trips into
    one. Folder is optional; defaults to a workspace's "AI Drafts" folder
    that's auto-created on first use."""

    workspace_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    content: str = ""
    content_type: str = Field("markdown", pattern=r"^(markdown|html)$")
    audience: str = Field("link", pattern=r"^(link|public)$")
    folder_id: UUID | None = None


class PublishResponse(BaseModel):
    page_id: UUID
    folder_id: UUID | None
    workspace_id: UUID
    visibility: str
    url: str
    view_id: UUID | None = None
    view_slug: str | None = None


# --- Files ---


class FileResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    folder_id: UUID | None = None
    name: str
    content_type: str
    size_bytes: int
    url: str
    uploaded_by: UUID
    created_at: datetime
    linked_table_id: UUID | None = None


class FileListResponse(BaseModel):
    files: list[FileResponse]


class SessionTranscriptResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    session_id: str
    agent_name: str
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


# --- Stashes ---


class StashCreateRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    agent_name: str = Field("", max_length=64)
    cwd: str | None = Field(None, max_length=1024)
    files_touched: list[str] = Field(default_factory=list)


class StashUpdateRequest(BaseModel):
    summary: str | None = None
    status: str | None = Field(None, pattern=r"^(live|summarizing|ready|failed)$")


class StashArtifactResponse(BaseModel):
    id: UUID
    file_path: str
    size_bytes: int
    created_at: datetime


class StashResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    session_id: str
    slug: str
    agent_name: str
    cwd: str | None
    status: str
    summary: str | None
    files_touched: list[str]
    artifact_count: int = 0
    has_transcript: bool = False
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class StashCreateResponse(BaseModel):
    id: UUID
    slug: str
    url: str
