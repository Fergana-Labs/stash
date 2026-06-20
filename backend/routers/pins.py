"""Per-user pins and recently-viewed items, scoped to a workspace.

Pins are an explicit per-kind set the user curates (skills / sessions /
files); recents are stamped automatically as the user opens things. Both are
private to the user. Pins require workspace membership; recents can also be
stamped by non-members for objects shared with them.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..database import get_pool
from ..services import permission_service, user_scope_service

router = APIRouter(prefix="/api/v1/workspaces/{owner_user_id}", tags=["pins"])

PIN_KINDS = {"skills", "sessions", "files"}
RECENTS_LIMIT = 24


async def _require_member(owner_user_id: UUID, user_id: UUID) -> None:
    if not await user_scope_service.is_member(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


async def _require_member_or_readable(
    owner_user_id: UUID, user_id: UUID, kind: str, object_id: str
) -> None:
    """Members can stamp anything; non-members only objects shared with them.

    Lets opening a shared page/file/folder record a recent in the object's
    home workspace, which powers the Shared-with-me Recent strip.
    """
    if await user_scope_service.is_member(owner_user_id, user_id):
        return
    try:
        parsed_id = UUID(object_id)
    except ValueError:
        raise HTTPException(status_code=403, detail="Not a workspace member")
    readable = await permission_service.check_access(
        kind, parsed_id, user_id, owner_user_id=owner_user_id
    )
    if not readable:
        raise HTTPException(status_code=403, detail="Not a workspace member")


class SetPinsRequest(BaseModel):
    ids: list[str]


class RecordRecentRequest(BaseModel):
    object_id: str
    kind: str = ""


@router.get("/pins")
async def get_pins(
    owner_user_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> dict[str, list[str]]:
    await _require_member(owner_user_id, current_user["id"])
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT kind, object_ids FROM user_pins WHERE user_id = $1 AND owner_user_id = $2",
        current_user["id"],
        owner_user_id,
    )
    result: dict[str, list[str]] = {kind: [] for kind in PIN_KINDS}
    for row in rows:
        if row["kind"] not in result:
            continue
        # The pool hands jsonb back as a raw string; parse to a list.
        value = row["object_ids"]
        result[row["kind"]] = json.loads(value) if isinstance(value, str) else value
    return result


@router.put("/pins/{kind}", status_code=204)
async def set_pins(
    owner_user_id: UUID,
    kind: str,
    req: SetPinsRequest,
    current_user: dict = Depends(get_current_user),
) -> None:
    if kind not in PIN_KINDS:
        raise HTTPException(status_code=400, detail="Unknown pin kind")
    await _require_member(owner_user_id, current_user["id"])
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO user_pins (user_id, owner_user_id, kind, object_ids, updated_at)
        VALUES ($1, $2, $3, $4::jsonb, now())
        ON CONFLICT (user_id, owner_user_id, kind)
        DO UPDATE SET object_ids = EXCLUDED.object_ids, updated_at = now()
        """,
        current_user["id"],
        owner_user_id,
        kind,
        json.dumps(req.ids),
    )


@router.get("/recents")
async def get_recents(
    owner_user_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    await _require_member(owner_user_id, current_user["id"])
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT object_id, kind FROM user_recents "
        "WHERE user_id = $1 AND owner_user_id = $2 "
        "ORDER BY viewed_at DESC LIMIT $3",
        current_user["id"],
        owner_user_id,
        RECENTS_LIMIT,
    )
    return [{"object_id": r["object_id"], "kind": r["kind"]} for r in rows]


@router.post("/recents", status_code=204)
async def record_recent(
    owner_user_id: UUID,
    req: RecordRecentRequest,
    current_user: dict = Depends(get_current_user),
) -> None:
    await _require_member_or_readable(owner_user_id, current_user["id"], req.kind, req.object_id)
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO user_recents (user_id, owner_user_id, object_id, kind, viewed_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (user_id, owner_user_id, object_id)
        DO UPDATE SET viewed_at = now(), kind = EXCLUDED.kind
        """,
        current_user["id"],
        owner_user_id,
        req.object_id,
        req.kind,
    )
