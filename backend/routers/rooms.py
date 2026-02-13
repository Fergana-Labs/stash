import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_user, get_current_user_optional
from ..models import (
    AccessListRequest,
    RoomCreateRequest,
    RoomListResponse,
    RoomMember,
    RoomResponse,
    RoomUpdateRequest,
)
from ..services import room_service, message_service, user_service, webhook_service
from ..services.connection_manager import manager

router = APIRouter(prefix="/api/v1/rooms", tags=["rooms"])


@router.post("", response_model=RoomResponse, status_code=201)
async def create_room(
    req: RoomCreateRequest, current_user: dict = Depends(get_current_user)
):
    room = await room_service.create_room(
        name=req.name,
        description=req.description,
        creator_id=current_user["id"],
        is_public=req.is_public,
        type=req.type,
    )
    return RoomResponse(**room)


@router.get("", response_model=RoomListResponse)
async def list_public_rooms():
    rooms = await room_service.list_public_rooms()
    return RoomListResponse(rooms=[RoomResponse(**r) for r in rooms])


@router.get("/mine", response_model=RoomListResponse)
async def list_my_rooms(current_user: dict = Depends(get_current_user)):
    rooms = await room_service.list_user_rooms(current_user["id"])
    return RoomListResponse(rooms=[RoomResponse(**r) for r in rooms])


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: UUID,
    current_user: dict | None = Depends(get_current_user_optional),
):
    room = await room_service.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not room["is_public"] and current_user:
        is_member = await room_service.is_member(room_id, current_user["id"])
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member of this room")
    return RoomResponse(**room)


@router.post("/join/{invite_code}", response_model=RoomResponse)
async def join_room(invite_code: str, current_user: dict = Depends(get_current_user)):
    room = await room_service.get_room_by_invite_code(invite_code)
    if not room:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    try:
        joined = await room_service.join_room(
            room["id"], current_user["id"], user_name=current_user["name"]
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if joined:
        # Send system message
        msg = await message_service.send_message(
            room_id=room["id"],
            sender_id=current_user["id"],
            content=f"{current_user['display_name'] or current_user['name']} joined the room",
            message_type="system",
        )
        event = {"type": "message", **msg}
        await manager.broadcast(room["id"], event)
        asyncio.create_task(webhook_service.dispatch_webhooks(room["id"], event, sender_id=current_user["id"]))
    return RoomResponse(**room)


@router.post("/{room_id}/leave")
async def leave_room(room_id: UUID, current_user: dict = Depends(get_current_user)):
    left = await room_service.leave_room(room_id, current_user["id"])
    if not left:
        raise HTTPException(status_code=400, detail="Not a member of this room")
    # Send system message
    msg = await message_service.send_message(
        room_id=room_id,
        sender_id=current_user["id"],
        content=f"{current_user['display_name'] or current_user['name']} left the room",
        message_type="system",
    )
    event = {"type": "message", **msg}
    await manager.broadcast(room_id, event)
    asyncio.create_task(webhook_service.dispatch_webhooks(room_id, event, sender_id=current_user["id"]))
    return {"ok": True}


@router.get("/{room_id}/members", response_model=list[RoomMember])
async def get_members(room_id: UUID, current_user: dict = Depends(get_current_user)):
    if not await room_service.is_member(room_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this room")
    members = await room_service.get_members(room_id)
    return [RoomMember(**m) for m in members]


@router.delete("/{room_id}")
async def delete_room(room_id: UUID, current_user: dict = Depends(get_current_user)):
    deleted = await room_service.delete_room(room_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=403, detail="Only the room owner can delete a room"
        )
    return {"ok": True}


@router.post("/{room_id}/kick/{user_id}")
async def kick_member(
    room_id: UUID, user_id: UUID, current_user: dict = Depends(get_current_user)
):
    try:
        await room_service.kick_member(room_id, current_user["id"], user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Send system message — look up the kicked user's name
    target_user = await user_service.get_user_by_id(user_id)
    target_name = (
        (target_user["display_name"] or target_user["name"])
        if target_user
        else "Unknown"
    )
    requester_name = current_user["display_name"] or current_user["name"]
    msg = await message_service.send_message(
        room_id=room_id,
        sender_id=current_user["id"],
        content=f"{requester_name} kicked {target_name} from the room",
        message_type="system",
    )
    event = {"type": "message", **msg}
    await manager.broadcast(room_id, event)
    asyncio.create_task(webhook_service.dispatch_webhooks(room_id, event, sender_id=current_user["id"]))
    return {"ok": True}


@router.patch("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: UUID,
    req: RoomUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        room = await room_service.update_room(
            room_id, current_user["id"], name=req.name, description=req.description
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return RoomResponse(**room)


@router.post("/{room_id}/access-list")
async def add_access_list_entry(
    room_id: UUID,
    req: AccessListRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        added = await room_service.add_to_access_list(
            room_id, current_user["id"], req.user_name, req.list_type
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"ok": True, "added": added}


@router.delete("/{room_id}/access-list")
async def remove_access_list_entry(
    room_id: UUID,
    req: AccessListRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        removed = await room_service.remove_from_access_list(
            room_id, current_user["id"], req.user_name, req.list_type
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not removed:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True}


@router.get("/{room_id}/access-list/{list_type}")
async def get_access_list(
    room_id: UUID,
    list_type: str,
    current_user: dict = Depends(get_current_user),
):
    if list_type not in ("allow", "block"):
        raise HTTPException(status_code=400, detail="list_type must be 'allow' or 'block'")
    role = await room_service.get_member_role(room_id, current_user["id"])
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the room owner can view access lists")
    entries = await room_service.get_access_list(room_id, list_type)
    return {"list_type": list_type, "entries": entries}
