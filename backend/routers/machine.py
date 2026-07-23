"""The user's cloud computer: interactive terminal + read-through file browsing.

The filesystem endpoints are a projection, not a sync: nothing is copied into
the DB except through the explicit save-to-Stash action, which routes through
the normal upload path so shares/extraction behave like any other upload.

The browser's WebSocket can't carry an Authorization header, so the bearer
token rides a query parameter. The backend holds both sockets and pumps
bytes between them — the Sprites org token never reaches the browser.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import mimetypes
import posixpath
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from ..auth import authenticate_token, get_current_user
from ..services import security_audit_service, sprite_service
from .files import ingest_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/me/machine", tags=["machine"])


async def _existing_sprite(user_id) -> sprite_service.Sprite:
    """The user's provisioned computer, or 404. Browsing must never provision
    a VM — only agent turns and the terminal do."""
    sprite = await sprite_service.existing(user_id)
    if sprite is None:
        raise HTTPException(status_code=404, detail="No cloud computer provisioned")
    return sprite


@router.get("/fs")
async def list_machine_dir(path: str = "", current_user: dict = Depends(get_current_user)):
    """Directory listing on the user's computer, path relative to the agent's
    working folder."""
    sprite = await _existing_sprite(current_user["id"])
    try:
        entries = await sprite_service.fs_list(sprite, path)
    except sprite_service.FsPathError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except sprite_service.SpriteError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    await security_audit_service.record_entries_listed(
        target_type="machine",
        actor_user_id=current_user["id"],
        owner_user_id=current_user["id"],
        metadata={
            "path_hash": security_audit_service.hash_value(path),
            "result_count": len(entries),
        },
    )
    return {"path": path, "entries": entries}


@router.get("/fs/file")
async def read_machine_file(path: str, current_user: dict = Depends(get_current_user)):
    """A file's content from the user's computer (capped; read-only)."""
    sprite = await _existing_sprite(current_user["id"])
    try:
        content = await sprite_service.fs_read(sprite, path)
    except sprite_service.FsPathError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except sprite_service.SpriteError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    # Live-machine paths can carry PII, so redact like source refs.
    await security_audit_service.record_content_read(
        target_type="machine_file",
        target_id=None,
        actor_user_id=current_user["id"],
        owner_user_id=current_user["id"],
        metadata={"path_hash": security_audit_service.hash_value(path)},
    )
    try:
        text = content.decode("utf-8")
        return {"path": path, "size": len(content), "text": text}
    except UnicodeDecodeError:
        return {
            "path": path,
            "size": len(content),
            "content_base64": base64.b64encode(content).decode(),
        }


class SaveToStashRequest(BaseModel):
    path: str
    folder_id: UUID | None = None


@router.post("/fs/save-to-stash")
async def save_machine_file_to_stash(
    req: SaveToStashRequest, current_user: dict = Depends(get_current_user)
):
    """Copy-on-share: the only way bytes leave the machine for the DB."""
    sprite = await _existing_sprite(current_user["id"])
    try:
        content = await sprite_service.fs_read(sprite, req.path)
    except sprite_service.FsPathError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except sprite_service.SpriteError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    filename = posixpath.basename(req.path) or "file"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return await ingest_bytes(
        owner_user_id=current_user["id"],
        user_id=current_user["id"],
        filename=filename,
        content=content,
        content_type=content_type,
        folder_id=req.folder_id,
    )


@router.websocket("/terminal")
async def terminal(ws: WebSocket, token: str = "", cols: int = 80, rows: int = 24):
    try:
        user = await authenticate_token(token)
    except HTTPException:
        await ws.close(code=4401, reason="Invalid token")
        return
    # This websocket authenticates outside get_current_user, so the read-key
    # gate must be applied here too — a shell is unrestricted write access.
    if user["key_access"] == "read":
        await ws.close(code=4403, reason="Read-only API key cannot open a terminal")
        return
    await ws.accept()

    try:
        sprite = await sprite_service.acquire(user["id"])
        term = await sprite_service.open_terminal(sprite, cols=cols, rows=rows)
    except Exception:
        logger.exception("terminal: failed to open shell for user %s", user["id"])
        await ws.close(code=1011, reason="Could not reach your computer")
        return

    async def pump_output() -> None:
        async for data in term.output():
            await ws.send_bytes(data)
        await ws.close(code=1000, reason="Shell exited")

    output_task = asyncio.create_task(pump_output())
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg["type"] == "input":
                await term.send_input(msg["data"].encode())
            elif msg["type"] == "resize":
                await term.resize(int(msg["cols"]), int(msg["rows"]))
    except WebSocketDisconnect:
        pass
    finally:
        # Close the box side first, unconditionally — awaiting the pump can
        # re-raise its own send error, and a leaked sprite exec keeps the box
        # awake (defeating sleep-to-zero).
        await term.close()
        output_task.cancel()
        with contextlib.suppress(Exception):
            await output_task
