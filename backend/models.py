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
    description: str = Field("", max_length=50000)


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=50000)
    cover_image_url: str | None = None
    icon_url: str | None = None
    color_gradient: str | None = Field(None, max_length=256)


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: str
    creator_id: UUID
    invite_code: str
    created_at: datetime
    updated_at: datetime
    member_count: int | None = None
    cover_image_url: str | None = None
    icon_url: str | None = None
    color_gradient: str | None = None


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceResponse]


# --- Stashes (publishable subsets of a workspace) ---

StashObjectType = str  # 'folder' | 'page' | 'table' | 'file' | 'session'


class StashItem(BaseModel):
    object_type: StashObjectType = Field(..., pattern=r"^(folder|page|table|file|session)$")
    object_id: UUID
    position: int = 0
    label_override: str | None = Field(None, max_length=160)


class StashCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: str = Field("", max_length=2000)
    access: str = Field("workspace", pattern=r"^(workspace|private|public)$")
    discoverable: bool = False
    cover_image_url: str | None = None
    icon_url: str | None = None
    items: list[StashItem] = Field(default_factory=list)


class StashUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=160)
    description: str | None = Field(None, max_length=2000)
    access: str | None = Field(None, pattern=r"^(workspace|private|public)$")
    discoverable: bool | None = None
    cover_image_url: str | None = None
    icon_url: str | None = None
    items: list[StashItem] | None = None


class StashResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    slug: str
    title: str
    description: str
    owner_id: UUID
    access: str
    discoverable: bool
    cover_image_url: str | None = None
    icon_url: str | None = None
    view_count: int
    items: list[StashItem]
    is_external: bool = False
    added_to_workspace_id: UUID | None = None
    forked_from_stash_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class StashListResponse(BaseModel):
    stashes: list[StashResponse]


class StashMemberRequest(BaseModel):
    user_id: UUID
    permission: str = Field("read", pattern=r"^(read|write|admin)$")


class StashSharePersonRequest(BaseModel):
    user_id: UUID | None = None
    username: str | None = Field(None, min_length=1, max_length=64)
    permission: str = Field("read", pattern=r"^(read|write|admin)$")


class StashShareUpdateRequest(BaseModel):
    access: str | None = Field(None, pattern=r"^(workspace|private|public)$")
    discoverable: bool | None = None
    people: list[StashSharePersonRequest] = Field(default_factory=list)
    remove_user_ids: list[UUID] = Field(default_factory=list)


class StashMemberResponse(BaseModel):
    user_id: UUID
    name: str
    display_name: str | None
    permission: str
    granted_by: UUID | None
    created_at: datetime


class StashMembersResponse(BaseModel):
    members: list[StashMemberResponse]


class StashShareOwnerResponse(BaseModel):
    user_id: UUID
    name: str
    display_name: str | None


class StashShareResponse(BaseModel):
    stash: StashResponse
    url: str
    owner: StashShareOwnerResponse
    members: list[StashMemberResponse]


# Public renderer payload — items are inlined with their content where it
# makes sense (folders/pages, table rows, file metadata, session events).
# The shape is intentionally permissive: each entry has the item
# type/id/label plus an `inline` blob whose contents depend on the type.


class StashItemInlined(BaseModel):
    object_type: StashObjectType
    object_id: UUID
    position: int
    label: str
    inline: dict


class StashPublicResponse(BaseModel):
    stash: StashResponse
    workspace_name: str
    items: list[StashItemInlined]
    can_write: bool = False
    can_manage_access: bool = False


class AddExternalStashRequest(BaseModel):
    workspace_id: UUID


class StashInviteResponse(BaseModel):
    id: UUID
    stash_id: UUID
    stash_slug: str
    stash_title: str
    stash_description: str
    source_workspace_id: UUID
    source_workspace_name: str
    invited_by_user_id: UUID
    invited_by_name: str
    invited_by_display_name: str | None = None
    permission: str
    created_at: datetime


class StashInviteListResponse(BaseModel):
    invites: list[StashInviteResponse]


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


# --- Files: folders (nested) and pages ---


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
    html_layout: str = Field("responsive", pattern=r"^(responsive|fixed-aspect)$")


class PageUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    folder_id: UUID | None = None
    content: str | None = None
    content_type: str | None = Field(None, pattern=r"^(markdown|html)$")
    content_html: str | None = None
    html_layout: str | None = Field(None, pattern=r"^(responsive|fixed-aspect)$")
    move_to_root: bool = False


class PageResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    folder_id: UUID | None
    name: str
    content_markdown: str
    content_type: str = "markdown"
    content_html: str = ""
    html_layout: str = "responsive"
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
    """Flat reference to a page for workspace-wide search and pickers.

    folder_path is the chain of folder names from the workspace root down to
    the immediate parent — empty for root pages, ['Architecture', 'API'] for
    a page nested two folders deep. Used to render and resolve
    Folder path is included so callers can display disambiguated page names.
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
    default_stash_id: UUID | None = None
    tool_name: str | None = Field(None, max_length=128)
    metadata: dict = Field(default_factory=dict)
    attachments: list[Attachment] | None = None
    created_at: datetime | None = Field(
        None, description="ISO timestamp; defaults to now if omitted"
    )


class HistoryEventBatchRequest(BaseModel):
    events: list[HistoryEventCreateRequest] = Field(..., min_length=1, max_length=100)
    default_stash_id: UUID | None = None


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
    rank: float | None = None


class HistoryEventListResponse(BaseModel):
    events: list[HistoryEventResponse]
    has_more: bool


class HistoryQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(20, ge=1, le=100)


class HistoryQueryResponse(BaseModel):
    answer: str
    sources: list[HistoryEventResponse]


class PublishRequest(BaseModel):
    """Single-call publish: create a Page from supplied content, wrap it in a
    Stash, and return the Stash URL. Folder is optional; defaults to a
    workspace's "AI Drafts" folder that's auto-created on first use."""

    workspace_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    content: str = ""
    content_type: str = Field("markdown", pattern=r"^(markdown|html)$")
    html_layout: str = Field("responsive", pattern=r"^(responsive|fixed-aspect)$")
    audience: str = Field("public", pattern=r"^(workspace|private|public)$")
    folder_id: UUID | None = None


class PublishResponse(BaseModel):
    page_id: UUID
    folder_id: UUID | None
    workspace_id: UUID
    visibility: str
    url: str
    stash_id: UUID | None = None
    stash_slug: str | None = None


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


class FileUpdateRequest(BaseModel):
    folder_id: UUID | None = None
    move_to_root: bool = False
    name: str | None = None


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
