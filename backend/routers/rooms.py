from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_user, get_current_user_optional
from ..models import RoomCreateRequest, RoomListResponse, RoomMember, RoomResponse
from ..services import room_service, message_service
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
    joined = await room_service.join_room(room["id"], current_user["id"])
    if joined:
        # Send system message
        msg = await message_service.send_message(
            room_id=room["id"],
            sender_id=current_user["id"],
            content=f"{current_user['display_name'] or current_user['name']} joined the room",
            message_type="system",
        )
        await manager.broadcast(room["id"], {"type": "message", **msg})
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
    await manager.broadcast(room_id, {"type": "message", **msg})
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
