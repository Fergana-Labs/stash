"""Pydantic request/response models for the REST API.

These mirror `backend/exports/native/spec.py` (BBox, Paragraph, TextRun) on
purpose so the sandbox can `dataclasses.asdict` a SlideSpec and post it
without writing a translation layer.
"""

from typing import Literal

from pydantic import BaseModel, Field


class BBoxModel(BaseModel):
    x: float
    y: float
    w: float
    h: float


class TextRunModel(BaseModel):
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_size_px: float = 16.0
    font_family: str = ""
    color: str = "#000000"


class ParagraphModel(BaseModel):
    runs: list[TextRunModel] = Field(default_factory=list)
    align: Literal["left", "center", "right", "justify"] = "left"
    line_height: float = 1.2


class CreateSessionRequest(BaseModel):
    # CSS px of the whole slide canvas. Matches layout_probe (1920x1080).
    slide_width_px: float = 1920.0
    slide_height_px: float = 1080.0


class CreateSessionResponse(BaseModel):
    session_id: str


class AddSlideRequest(BaseModel):
    bg_color: str | None = None  # hex like "#ffffff"; None → white


class AddSlideResponse(BaseModel):
    slide_index: int


class TextShapeRequest(BaseModel):
    bbox: BBoxModel
    paragraphs: list[ParagraphModel] = Field(default_factory=list)
    bg_color: str | None = None
    # top, right, bottom, left — CSS px
    padding_px: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


class ImageShapeRequest(BaseModel):
    bbox: BBoxModel
    # base64-encoded image bytes (png/jpg/etc)
    image_base64: str


class TableShapeRequest(BaseModel):
    bbox: BBoxModel
    # rows × cols of cell text content (each cell is a single paragraph)
    cells: list[list[ParagraphModel]] = Field(default_factory=list)


class ShapeResponse(BaseModel):
    shape_index: int
