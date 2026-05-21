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

ShapeKind = Literal["text", "image", "table", "raster"]
TextAlign = Literal["left", "center", "right", "justify"]


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

    # table:
    cells: list[list[ShapeSpec]] = field(default_factory=list)

    # raster fallback:
    raster_selector: str | None = None  # CSS selector inside the slide
    raster_reason: str | None = None


@dataclass
class SlideSpec:
    """Everything needed to build one PPTX slide."""

    index: int
    bg_color: str | None = None  # solid background; if None, builder defaults to white
    bg_raster_selector: str | None = None  # set when background is a gradient / image
    shapes: list[ShapeSpec] = field(default_factory=list)
