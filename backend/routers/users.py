from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import get_current_user
from ..middleware import limiter
from ..models import (
    LoginRequest,
    UserProfile,
    UserRegisterRequest,
    UserRegisterResponse,
    UserSearchResult,
    UserUpdateRequest,
)
from ..services import user_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.post("/register", response_model=UserRegisterResponse, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, req: UserRegisterRequest):
    try:
        user, api_key = await user_service.register_user(
            name=req.name,
            display_name=req.display_name,
            user_type="human",
            description=req.description,
            password=req.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return UserRegisterResponse(
        id=user["id"],
        name=user["name"],
        display_name=user["display_name"],
        type=user["type"],
        api_key=api_key,
    )


@router.post("/login", response_model=UserRegisterResponse)
@limiter.limit("10/minute")
async def login(request: Request, req: LoginRequest):
    try:
        user, api_key = await user_service.authenticate_by_password(
            name=req.name, password=req.password
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
        )
    return UserRegisterResponse(
        id=user["id"],
        name=user["name"],
        display_name=user["display_name"],
        type=user["type"],
        api_key=api_key,
    )


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserProfile(**current_user)


@router.patch("/me", response_model=UserProfile)
async def update_me(
    req: UserUpdateRequest, current_user: dict = Depends(get_current_user)
):
    updated = await user_service.update_user(
        user_id=current_user["id"],
        display_name=req.display_name,
        description=req.description,
        password=req.password,
    )
    return UserProfile(**updated)


@router.get("/search", response_model=list[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=1, max_length=64),
    current_user: dict = Depends(get_current_user),
):
    """Search for users by name or display name."""
    from ..database import get_pool
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, display_name, type FROM users "
        "WHERE (name ILIKE $1 OR display_name ILIKE $1) AND id != $2 "
        "LIMIT 20",
        f"%{q}%",
        current_user["id"],
    )
    return [UserSearchResult(**dict(r)) for r in rows]
