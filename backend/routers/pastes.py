"""Public pastes router — the joinstash.ai/pages pastebin.

Fully anonymous: creation and edits are IP rate-limited rather than
authenticated. Publishing returns two URLs — the public view link and a
private edit link whose token is the only write credential, passed as a
``?token=`` query param so the www edit URL can forward it verbatim.
Reads support ``?format=raw`` so agents can curl the source directly.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..middleware import limiter
from ..services import paste_service

router = APIRouter(prefix="/api/v1/pastes", tags=["pastes"])

_CONTENT_MAX = 512_000


class PasteCreateRequest(BaseModel):
    title: str = Field("", max_length=200)
    content: str = Field(..., min_length=1, max_length=_CONTENT_MAX)
    content_type: str = Field(..., pattern=r"^(markdown|html)$")
    # 'public' shows in the feed; 'unlisted' is link-only. There is no
    # 'private' — that's the signup gate into the product.
    visibility: str = Field("public", pattern=r"^(public|unlisted)$")


class PasteUpdateRequest(BaseModel):
    # Empty fields mean "leave unchanged" so content saves and the
    # comments toggle share one endpoint.
    title: str = Field("", max_length=200)
    content: str = Field("", max_length=_CONTENT_MAX)
    comments_enabled: bool | None = None


class CommentCreateRequest(BaseModel):
    author_name: str = Field("", max_length=60)
    body: str = Field(..., min_length=1, max_length=5_000)
    quoted_text: str = Field("", max_length=500)
    prefix: str = Field("", max_length=100)
    suffix: str = Field("", max_length=100)


@router.post("", status_code=201)
@limiter.limit("10/minute")
async def create_paste(request: Request, body: PasteCreateRequest) -> dict:
    return await paste_service.create_paste(
        body.title, body.content, body.content_type, body.visibility
    )


@router.get("")
@limiter.limit("60/minute")
async def list_pastes(request: Request) -> dict:
    return {"pastes": await paste_service.list_recent()}


@router.get("/{slug}")
@limiter.limit("120/minute")
async def get_paste(request: Request, slug: str, format: str = ""):
    paste = await paste_service.get_paste(slug)
    if not paste:
        raise HTTPException(status_code=404, detail="Paste not found")
    if format == "raw":
        media_type = "text/markdown" if paste["content_type"] == "markdown" else "text/plain"
        return PlainTextResponse(paste["content"], media_type=media_type)
    return paste


@router.patch("/{slug}")
@limiter.limit("30/minute")
async def update_paste(request: Request, slug: str, token: str, body: PasteUpdateRequest) -> dict:
    paste = await paste_service.update_paste(
        slug, token, body.title, body.content, body.comments_enabled
    )
    if not paste:
        raise HTTPException(status_code=404, detail="Paste not found")
    return paste


@router.delete("/{slug}", status_code=204)
@limiter.limit("30/minute")
async def delete_paste(request: Request, slug: str, token: str) -> None:
    if not await paste_service.delete_paste(slug, token):
        raise HTTPException(status_code=404, detail="Paste not found")


@router.get("/{slug}/comments")
@limiter.limit("120/minute")
async def list_comments(request: Request, slug: str) -> dict:
    return {"comments": await paste_service.list_comments(slug)}


@router.post("/{slug}/comments", status_code=201)
@limiter.limit("10/minute")
async def add_comment(request: Request, slug: str, body: CommentCreateRequest) -> dict:
    comment = await paste_service.add_comment(
        slug, body.author_name, body.body, body.quoted_text, body.prefix, body.suffix
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Paste not found")
    return comment


class CommentUpdateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=5_000)


@router.patch("/{slug}/comments/{comment_id}")
@limiter.limit("30/minute")
async def update_comment(
    request: Request, slug: str, comment_id: str, token: str, body: CommentUpdateRequest
) -> dict:
    if not token:
        raise HTTPException(status_code=404, detail="Comment not found")
    comment = await paste_service.update_comment(slug, comment_id, token, body.body)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment


@router.delete("/{slug}/comments/{comment_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_comment(request: Request, slug: str, comment_id: str, token: str) -> None:
    if not token:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not await paste_service.delete_comment(slug, comment_id, token):
        raise HTTPException(status_code=404, detail="Comment not found")
