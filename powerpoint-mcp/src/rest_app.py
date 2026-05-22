"""FastAPI REST layer in front of Aspose.Slides.

Session-based per-element build: create a session → add slides → add
shapes → fetch PPTX bytes → delete. Designed for the moltchat native
export sandbox to drive over HTTP from a Mac (Aspose.Slides for Python
needs the Linux/.NET runtime, so this service runs in Docker on Render
and the sandbox talks to it remotely).
"""

from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Header, Response
from pydantic import BaseModel

from . import builder
from .models import (
    AddSlideRequest,
    AddSlideResponse,
    ChartShapeRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    ImageShapeRequest,
    ShapeResponse,
    SvgShapeRequest,
    TableShapeRequest,
    TextShapeRequest,
)
from .session_manager import get_session_manager

logger = logging.getLogger(__name__)

# Canvas dims declared at session create. Keyed by session_id; entries
# evicted alongside the session by the session manager's LRU/TTL —
# stale entries here are harmless (the underlying session is gone).
_canvas_dims: dict[str, tuple[float, float]] = {}


app = FastAPI(title="aspose-pptx", version="0.1.0")


def _check_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ASPOSE_PPTX_TOKEN")
    if not expected:
        return  # No token configured → open access (local/dev).
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(status_code=403, detail="invalid bearer token")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/sessions", response_model=CreateSessionResponse,
          dependencies=[Depends(_check_token)])
def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
    manager = get_session_manager()
    session = manager.create_empty_session(file_name="export.pptx")
    builder._set_canvas_size(session.presentation, req.slide_width_px, req.slide_height_px)
    # Aspose's empty presentation seeds one slide we don't want; drop it
    # so add_slide indexes start at 0.
    pres = session.presentation
    while pres.slides.length > 0:
        pres.slides.remove_at(0)

    _canvas_dims[session.session_id] = (req.slide_width_px, req.slide_height_px)
    return CreateSessionResponse(session_id=session.session_id)


@app.delete("/sessions/{session_id}", dependencies=[Depends(_check_token)])
def delete_session(session_id: str) -> dict:
    get_session_manager().close_session(session_id)
    _canvas_dims.pop(session_id, None)
    return {"ok": True}


@app.post("/sessions/{session_id}/slides", response_model=AddSlideResponse,
          dependencies=[Depends(_check_token)])
def add_slide(session_id: str, req: AddSlideRequest) -> AddSlideResponse:
    pres = _get_presentation(session_id)
    index = builder.add_blank_slide(pres, req.bg_color, req.bg_gradient)
    return AddSlideResponse(slide_index=index)


@app.post("/sessions/{session_id}/slides/{slide_index}/text",
          response_model=ShapeResponse,
          dependencies=[Depends(_check_token)])
def add_text(session_id: str, slide_index: int, req: TextShapeRequest) -> ShapeResponse:
    pres = _get_presentation(session_id)
    cw, ch = _get_canvas(session_id)
    idx = builder.add_text_shape(pres, slide_index, req, cw, ch)
    return ShapeResponse(shape_index=idx)


@app.post("/sessions/{session_id}/slides/{slide_index}/image",
          response_model=ShapeResponse,
          dependencies=[Depends(_check_token)])
def add_image(session_id: str, slide_index: int, req: ImageShapeRequest) -> ShapeResponse:
    pres = _get_presentation(session_id)
    cw, ch = _get_canvas(session_id)
    idx = builder.add_image_shape(pres, slide_index, req, cw, ch)
    return ShapeResponse(shape_index=idx)


@app.post("/sessions/{session_id}/slides/{slide_index}/raster",
          response_model=ShapeResponse,
          dependencies=[Depends(_check_token)])
def add_raster(session_id: str, slide_index: int, req: ImageShapeRequest) -> ShapeResponse:
    # Raster is just an image — the distinction is semantic (whole-element
    # fallback vs first-class picture). Aspose treats both as picture
    # frames; we keep the routes separate so the sandbox can stay
    # readable.
    return add_image(session_id, slide_index, req)


@app.post("/sessions/{session_id}/slides/{slide_index}/table",
          response_model=ShapeResponse,
          dependencies=[Depends(_check_token)])
def add_table(session_id: str, slide_index: int, req: TableShapeRequest) -> ShapeResponse:
    pres = _get_presentation(session_id)
    cw, ch = _get_canvas(session_id)
    idx = builder.add_table_shape(pres, slide_index, req, cw, ch)
    return ShapeResponse(shape_index=idx)


@app.post("/sessions/{session_id}/slides/{slide_index}/svg",
          response_model=ShapeResponse,
          dependencies=[Depends(_check_token)])
def add_svg(session_id: str, slide_index: int, req: SvgShapeRequest) -> ShapeResponse:
    pres = _get_presentation(session_id)
    cw, ch = _get_canvas(session_id)
    idx = builder.add_svg_shape(pres, slide_index, req, cw, ch)
    return ShapeResponse(shape_index=idx)


@app.post("/sessions/{session_id}/slides/{slide_index}/chart",
          response_model=ShapeResponse,
          dependencies=[Depends(_check_token)])
def add_chart(session_id: str, slide_index: int, req: ChartShapeRequest) -> ShapeResponse:
    pres = _get_presentation(session_id)
    cw, ch = _get_canvas(session_id)
    idx = builder.add_chart_shape(pres, slide_index, req, cw, ch)
    return ShapeResponse(shape_index=idx)


@app.get("/sessions/{session_id}/pptx", dependencies=[Depends(_check_token)])
def get_pptx(session_id: str) -> Response:
    pres = _get_presentation(session_id)
    pptx_bytes = builder.save_presentation_bytes(pres)
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="export.pptx"'},
    )


def _get_presentation(session_id: str):
    try:
        return get_session_manager().get_presentation(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _get_canvas(session_id: str) -> tuple[float, float]:
    dims = _canvas_dims.get(session_id)
    if dims is None:
        raise HTTPException(status_code=404, detail=f"canvas not found for session {session_id}")
    return dims
