from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# --- Users ---


class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str | None = Field(None, min_length=1, max_length=128)
    description: str = Field("", max_length=500)
    password: str | None = Field(None, min_length=8, max_length=128)
    # Optional: lets others share with this account by email and converts any
    # pending share invites addressed to it.
    email: str | None = Field(None, max_length=320)


class UserRegisterResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    api_key: str
    created: bool = False


class Auth0SessionResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    created: bool = False


class UserProfile(BaseModel):
    id: UUID
    name: str
    display_name: str
    email: str | None = None
    description: str
    created_at: datetime
    last_seen: datetime
    role: str | None = None
    referral_source: str | None = None
    use_case: str | None = None


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=500)
    password: str | None = Field(None, min_length=8, max_length=128)
    # Required whenever `password` is set — stops a stolen session key from
    # being enough to permanently take over the account.
    current_password: str | None = Field(None, max_length=128)
    # Captured during onboarding's first step.
    role: str | None = Field(None, max_length=128)
    referral_source: str | None = Field(None, max_length=128)
    use_case: str | None = Field(None, max_length=2000)


class LoginRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserSearchResult(BaseModel):
    id: UUID
    name: str
    display_name: str


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
    is_primary: bool = False


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceResponse]


# --- Skills (special folders + their publish records) ---

SkillGeneralPermission = str  # 'none' | 'read' | 'write'


class SkillPublishRequest(BaseModel):
    folder_id: UUID
    title: str | None = Field(None, min_length=1, max_length=160)
    description: str = Field("", max_length=2000)
    discoverable: bool = False
    cover_image_url: str | None = None
    icon_url: str | None = None


class SkillUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=160)
    description: str | None = Field(None, max_length=2000)
    discoverable: bool | None = None
    cover_image_url: str | None = None
    icon_url: str | None = None


class SkillResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    folder_id: UUID
    slug: str
    title: str
    description: str
    owner_id: UUID
    owner_name: str
    owner_display_name: str | None = None
    discoverable: bool
    cover_image_url: str | None = None
    icon_url: str | None = None
    source_github_url: str | None = None
    view_count: int
    created_at: datetime
    updated_at: datetime


# Public renderer payload — the skill's folder contents, inlined: pages carry
# their bodies, files presigned URLs, tables columns + rows.


class SkillPublicResponse(BaseModel):
    skill: SkillResponse
    workspace_name: str
    folder_name: str
    contents: dict
    can_write: bool = False


class ForkSkillRequest(BaseModel):
    workspace_id: UUID


class WorkspaceMember(BaseModel):
    user_id: UUID
    name: str
    display_name: str
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
    display_name: str
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
    html_layout: str = Field("responsive", pattern=r"^(responsive|fixed-aspect|full-width|app)$")


class PageUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    folder_id: UUID | None = None
    content: str | None = None
    collab_projection: bool = False
    content_type: str | None = Field(None, pattern=r"^(markdown|html)$")
    content_html: str | None = None
    html_layout: str | None = Field(None, pattern=r"^(responsive|fixed-aspect|full-width|app)$")
    move_to_root: bool = False


class CopyRequest(BaseModel):
    """Duplicate a page/folder/file into target_folder_id (defaults to the
    source's own folder when omitted)."""

    target_folder_id: UUID | None = None


class BatchItem(BaseModel):
    object_type: str
    object_id: UUID


class BatchMoveRequest(BaseModel):
    items: list[BatchItem]
    target_folder_id: UUID | None = None
    move_to_root: bool = False


class BatchRequest(BaseModel):
    items: list[BatchItem]


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
    last_edit_session_id: str | None = None
    last_edit_agent_name: str | None = None
    created_by: UUID
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime


class PageSummary(BaseModel):
    """Lightweight page entry used in workspace tree responses."""

    id: UUID
    name: str
    content_type: str
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


# --- Page comments ---


class CommentMessage(BaseModel):
    id: UUID
    thread_id: UUID
    author_id: UUID
    author_name: str
    body: str
    created_at: datetime


class CommentThread(BaseModel):
    id: UUID
    page_id: UUID
    quoted_text: str
    prefix: str
    suffix: str
    created_by: UUID
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: UUID | None
    orphaned: bool
    messages: list[CommentMessage] = []


class CommentThreadCreateRequest(BaseModel):
    quoted_text: str = Field(..., min_length=1, max_length=8000)
    prefix: str = Field("", max_length=128)
    suffix: str = Field("", max_length=128)
    body: str = Field(..., min_length=1, max_length=10000)


class CommentReplyRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)


class CommentResolveRequest(BaseModel):
    resolved: bool


class CommentReconcileRequest(BaseModel):
    present_ids: list[UUID] = Field(default_factory=list)


class CommentThreadListResponse(BaseModel):
    threads: list[CommentThread]


class WorkspacePageEntry(BaseModel):
    """Flat reference to a page for workspace-wide search and pickers.

    folder_path is the chain of folder names from the workspace root down to
    the immediate parent — empty for root pages, ['Architecture', 'API'] for
    a page nested two folders deep. Used to render and resolve
    Folder path is included so callers can display disambiguated page names.
    """

    id: UUID
    name: str
    content_type: str
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
    width: int = Field(180, ge=80, le=800)


class TableCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=1000)
    columns: list[ColumnDefinition] = Field(default_factory=list)
    folder_id: UUID | None = None


class TableUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    folder_id: UUID | None = None
    move_to_root: bool = False


class TableResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    folder_id: UUID | None = None
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
    width: int = Field(180, ge=80, le=800)


class ColumnUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    type: str | None = Field(
        None,
        pattern=r"^(text|number|boolean|date|datetime|url|email|select|multiselect|json)$",
    )
    required: bool | None = None
    default: str | int | float | bool | list | None = None
    options: list[str] | None = None
    width: int | None = Field(None, ge=80, le=800)


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
    session_folder_id: UUID | None = Field(
        None, description="Pinned folder for this session (from the repo manifest)"
    )
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

    workspace_id: UUID | None = None
    title: str = Field(..., min_length=1, max_length=255)
    content: str = ""
    content_type: str = Field("markdown", pattern=r"^(markdown|html)$")
    html_layout: str = Field("responsive", pattern=r"^(responsive|fixed-aspect|full-width|app)$")
    folder_id: UUID | None = None


class PublishResponse(BaseModel):
    page_id: UUID
    folder_id: UUID | None
    workspace_id: UUID
    url: str
    skill_id: UUID | None = None
    skill_slug: str | None = None


# --- Files ---


class FileResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    folder_id: UUID | None = None
    name: str
    content_type: str
    size_bytes: int
    url: str
    app_url: str
    uploaded_by: UUID
    uploaded_by_name: str
    uploaded_by_display_name: str | None = None
    created_at: datetime
    linked_table_id: UUID | None = None


class FileListResponse(BaseModel):
    files: list[FileResponse]


class FileUpdateRequest(BaseModel):
    folder_id: UUID | None = None
    move_to_root: bool = False
    name: str | None = None


class UploadResponse(BaseModel):
    """Result of POST /workspaces/{id}/files.

    Polymorphic: markdown and HTML uploads become pages (editable in-app);
    everything else becomes a binary file in S3. Callers branch on `kind`;
    common fields `id` / `name` / `app_url` work either way.
    """

    kind: Literal["file", "page"]
    id: UUID
    workspace_id: UUID
    folder_id: UUID | None = None
    name: str
    content_type: str
    app_url: str
    created_at: datetime
    # File-only
    size_bytes: int | None = None
    url: str | None = None
    uploaded_by: UUID | None = None
    linked_table_id: UUID | None = None
    # Page-only
    content_markdown: str | None = None
    content_html: str | None = None
    created_by: UUID | None = None


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
