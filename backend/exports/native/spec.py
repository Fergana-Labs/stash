"""Intermediate representation between layout_probe and pptx_builder.

A `SlideSpec` is everything we need to assemble one PPTX slide. Coords
are CSS pixels relative to the slide section's top-left, before any
canvas-CSS-injected zoom. The builder converts to EMU via the px_to_emu
helper in pptx_builder.py.

All dataclasses are JSON-serialisable via `dataclasses.asdict`, so we
can snapshot them in tests without writing a custom encoder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ShapeKind = Literal["text", "image", "table", "raster", "svg", "chart"]
TextAlign = Literal["left", "center", "right", "justify"]
GradientType = Literal["linear", "radial"]
ChartType = Literal["bar", "line", "pie", "doughnut", "area"]


@dataclass
class TextRun:
    """A run of inline text with uniform formatting — equivalent to one
    `<a:r>` element in PPTX. Multiple runs in a paragraph capture mixed
    inline styling (a bold word inside a normal sentence, etc.)."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_size_px: float = 16.0
    font_family: str = ""
    color: str = "#000000"  # hex like "#1A73E8"


@dataclass
class Paragraph:
    """One `<p>` / `<li>` / `<h1>` / etc. — a block of `TextRun`s with a
    shared alignment."""

    runs: list[TextRun] = field(default_factory=list)
    align: TextAlign = "left"
    line_height: float = 1.2


@dataclass
class BBox:
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h


@dataclass
class GradientStop:
    offset: float  # 0.0 → 1.0
    color: str  # hex


@dataclass
class Gradient:
    """Parsed CSS gradient. Aspose translates this to a native gradient
    fill so the bg stays vector instead of a stretched PNG."""

    type: GradientType = "linear"
    angle: float = 0.0  # CSS degrees, 0 = bottom-to-top
    stops: list[GradientStop] = field(default_factory=list)


@dataclass
class ChartDataset:
    label: str = ""
    data: list[float] = field(default_factory=list)
    color: str | None = None  # series fill / line color, hex
    line_width_px: float | None = None  # Chart.js borderWidth (line/area)
    point_radius_px: float | None = None  # Chart.js pointRadius (line/area)


@dataclass
class ChartSpec:
    """Extracted from `Chart.getChart(canvas).config` so Aspose can
    re-emit a native PPTX chart instead of embedding a canvas PNG."""

    type: ChartType = "bar"
    labels: list[str] = field(default_factory=list)
    datasets: list[ChartDataset] = field(default_factory=list)
    title: str = ""
    axis_font_size_px: float | None = None  # Chart.js tick font size


@dataclass
class ShapeSpec:
    """One PPTX shape. Discriminated by `kind`."""

    kind: ShapeKind
    bbox: BBox
    z: int = 0

    # text:
    paragraphs: list[Paragraph] = field(default_factory=list)
    bg_color: str | None = None  # for "card" rectangles (text shape with fill)
    padding_px: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # top, right, bottom, left

    # image:
    src: str | None = None

    # table: per-cell ShapeSpec (text-only); col_widths_px maps the table
    # bbox into per-column widths. border_* describe a uniform border to
    # apply on every cell (HTML's per-cell border is collapsed into one).
    cells: list[list[ShapeSpec]] = field(default_factory=list)
    col_widths_px: list[float] = field(default_factory=list)
    border_color: str | None = None
    border_width_px: float = 0.0

    # raster fallback:
    raster_selector: str | None = None  # CSS selector inside the slide
    raster_reason: str | None = None

    # svg: serialized <svg> outerHTML (vector passthrough to Aspose)
    svg: str | None = None

    # chart: parsed Chart.js config for native PPTX chart emission
    chart: ChartSpec | None = None


@dataclass
class SlideSpec:
    """Everything needed to build one PPTX slide."""

    index: int
    bg_color: str | None = None  # solid background; if None, builder defaults to white
    bg_gradient: Gradient | None = None  # native gradient — preferred over raster
    bg_raster_selector: str | None = None  # set when bg is image/pattern we can't parse
    shapes: list[ShapeSpec] = field(default_factory=list)
