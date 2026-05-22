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


class GradientStopModel(BaseModel):
    offset: float  # 0.0 → 1.0
    color: str


class GradientModel(BaseModel):
    type: Literal["linear", "radial"] = "linear"
    angle: float = 0.0  # CSS degrees
    stops: list[GradientStopModel] = Field(default_factory=list)


class AddSlideRequest(BaseModel):
    bg_color: str | None = None  # hex like "#ffffff"; None → white
    bg_gradient: GradientModel | None = None  # native gradient fill


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


class TableCellModel(BaseModel):
    paragraph: ParagraphModel = Field(default_factory=ParagraphModel)
    bg_color: str | None = None


class TableShapeRequest(BaseModel):
    bbox: BBoxModel
    # rows × cols of cell content (single paragraph per cell + optional bg)
    cells: list[list[TableCellModel]] = Field(default_factory=list)
    # Optional per-column widths in CSS px. When empty the builder falls
    # back to equal_split. Must equal len(cells[0]) when provided.
    col_widths_px: list[float] = Field(default_factory=list)
    border_color: str | None = None
    border_width_px: float = 0.0


class SvgShapeRequest(BaseModel):
    bbox: BBoxModel
    # raw SVG markup, not base64 — Aspose ingests it directly
    svg: str


class ChartDatasetModel(BaseModel):
    label: str = ""
    data: list[float] = Field(default_factory=list)
    color: str | None = None
    line_width_px: float | None = None  # Chart.js borderWidth, line/area only
    point_radius_px: float | None = None  # Chart.js pointRadius, line/area only


class ChartShapeRequest(BaseModel):
    bbox: BBoxModel
    type: Literal["bar", "line", "pie", "doughnut", "area"] = "bar"
    labels: list[str] = Field(default_factory=list)
    datasets: list[ChartDatasetModel] = Field(default_factory=list)
    title: str = ""
    # CSS px size for axis tick + category labels. Chart.js default is 12.
    axis_font_size_px: float | None = None


class ShapeResponse(BaseModel):
    shape_index: int
