"""API routes for ai-collab session history."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..models import (
    AICollabCommit,
    AICollabEvent,
    AICollabEventResponse,
    AICollabSessionResponse,
    AICollabSessionStart,
)
from ..services import ai_collab_service

router = APIRouter(prefix="/api/v1/ai-collab", tags=["ai-collab"])


@router.post("/sessions", status_code=201)
async def start_session(
    req: AICollabSessionStart,
    current_user: dict = Depends(get_current_user),
):
    """Create or update an AI session."""
    session = await ai_collab_service.upsert_session(
        session_id=req.session_id,
        user_id=str(current_user["id"]),
        user_name=current_user["name"],
        repo_url=req.repo_url,
        branch=req.branch,
        head_sha=req.head_sha,
        cwd=req.cwd,
    )
    return {"ok": True, "session_id": session["id"]}


@router.post("/sessions/{session_id}/end", status_code=200)
async def end_session(
    session_id: str,
    head_sha: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Mark a session as ended."""
    await ai_collab_service.end_session(session_id, head_sha=head_sha)
    return {"ok": True}


@router.post("/events", status_code=201)
async def record_event(
    req: AICollabEvent,
    current_user: dict = Depends(get_current_user),
):
    """Record a hook event."""
    event = await ai_collab_service.insert_event(
        session_id=req.session_id,
        event_type=req.event_type,
        head_sha=req.head_sha,
        data=req.data,
        summary=req.summary,
    )
    return {"ok": True, "event_id": event["id"]}


@router.post("/commits", status_code=201)
async def record_commit(
    req: AICollabCommit,
    current_user: dict = Depends(get_current_user),
):
    """Record a git commit made during an AI session."""
    await ai_collab_service.insert_commit(
        sha=req.sha,
        session_id=req.session_id,
        repo_url=req.repo_url,
        message=req.message,
        author=current_user["name"],
    )
    return {"ok": True}


@router.get("/sessions", response_model=list[AICollabSessionResponse])
async def list_sessions(
    repo_url: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    since_hours: int | None = Query(None, ge=1),
    branch: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """List recent AI sessions for a repository."""
    return await ai_collab_service.recent_sessions(
        repo_url=repo_url,
        limit=limit,
        since_hours=since_hours,
        branch=branch,
    )


@router.get("/sessions/{session_id}", response_model=AICollabSessionResponse)
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a specific session."""
    session = await ai_collab_service.session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/events", response_model=list[AICollabEventResponse])
async def get_session_events(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get all events for a session."""
    return await ai_collab_service.session_events(session_id)


@router.get("/commits/{sha}")
async def get_commit(
    sha: str,
    current_user: dict = Depends(get_current_user),
):
    """Get AI session context for a commit."""
    commit = await ai_collab_service.commit_by_sha(sha)
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")
    return commit


@router.get("/search", response_model=list[AICollabEventResponse])
async def search(
    q: str = Query(..., min_length=1),
    repo_url: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Full-text search over session activity."""
    return await ai_collab_service.search_events(
        repo_url=repo_url,
        query=q,
        limit=limit,
    )
