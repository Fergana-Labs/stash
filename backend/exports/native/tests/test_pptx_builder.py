"""Builder-level tests that bypass Playwright entirely.

We hand-build a `SlideSpec` and run it through `pptx_builder.build_pptx`,
then inspect the resulting OOXML to confirm:
    - Slides + sections + shapes are present.
    - Native text runs exist (selectable, not embedded in an image).
    - Padding / colour metadata makes it through.
"""

from __future__ import annotations

import asyncio
import io
import zipfile

from backend.exports.native.image_fetch import ImageFetcher
from backend.exports.native.pptx_builder import build_pptx, px_to_emu_x, px_to_emu_y
from backend.exports.native.spec import (
    BBox,
    Paragraph,
    ShapeSpec,
    SlideSpec,
    TextRun,
)


class _StubFetcher(ImageFetcher):
    """Image fetcher that returns nothing — keeps tests offline."""

    async def fetch(self, src):  # type: ignore[override]
        return None


def _build(specs: list[SlideSpec]) -> bytes:
    return asyncio.run(
        build_pptx(specs, html="<html><body></body></html>", image_fetcher=_StubFetcher())
    )


def test_px_to_emu_clamps_within_slide():
    # SLIDE_WIDTH_EMU == 12_192_000 — 1920 px maps to that exactly.
    assert px_to_emu_x(0) == 0
    assert px_to_emu_x(1920) == 12_192_000
    # Out-of-bounds clamps, doesn't blow up.
    assert px_to_emu_x(-10) == 0
    assert px_to_emu_x(9999) == 12_192_000
    assert px_to_emu_y(1080) == 6_858_000


def test_emits_native_text_run_with_formatting():
    spec = SlideSpec(
        index=0,
        bg_color="#1A73E8",
        shapes=[
            ShapeSpec(
                kind="text",
                bbox=BBox(x=64, y=64, w=1792, h=120),
                z=0,
                paragraphs=[
                    Paragraph(
                        runs=[
                            TextRun(
                                text="Well-formed slide",
                                bold=True,
                                font_size_px=96,
                                color="#FFFFFF",
                                font_family="Inter",
                            ),
                        ],
                        align="left",
                    )
                ],
            )
        ],
    )
    pptx = _build([spec])
    with zipfile.ZipFile(io.BytesIO(pptx)) as z:
        slide_xml = z.read("ppt/slides/slide1.xml").decode("utf-8")

    assert "<a:t>Well-formed slide</a:t>" in slide_xml, "text run should be present"
    assert "<a:rPr" in slide_xml, "run properties should be emitted"
    assert "FFFFFF" in slide_xml, "white color should survive"
    assert 'b="1"' in slide_xml, "bold attribute should be on the run"
    # No leftover invisible-text-overlay alpha hack from the screenshot exporter.
    assert "<a:alpha" not in slide_xml


def test_emits_card_background_as_rectangle():
    spec = SlideSpec(
        index=0,
        shapes=[
            ShapeSpec(
                kind="text",
                bbox=BBox(x=100, y=100, w=400, h=200),
                z=-1,
                paragraphs=[],
                bg_color="#FF0000",
            ),
        ],
    )
    pptx = _build([spec])
    with zipfile.ZipFile(io.BytesIO(pptx)) as z:
        slide_xml = z.read("ppt/slides/slide1.xml").decode("utf-8")
    # Rectangles use <p:sp> with a preset geometry of "rect".
    assert 'prstGeom prst="rect"' in slide_xml
    assert "FF0000" in slide_xml


def test_solid_background_lands_on_slide():
    spec = SlideSpec(index=0, bg_color="#0F172A", shapes=[])
    pptx = _build([spec])
    with zipfile.ZipFile(io.BytesIO(pptx)) as z:
        slide_xml = z.read("ppt/slides/slide1.xml").decode("utf-8")
    assert "0F172A" in slide_xml


def test_multiple_slides_get_distinct_xml():
    specs = [
        SlideSpec(index=0, bg_color="#000000", shapes=[]),
        SlideSpec(index=1, bg_color="#FFFFFF", shapes=[]),
    ]
    pptx = _build(specs)
    with zipfile.ZipFile(io.BytesIO(pptx)) as z:
        names = [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
    assert len(names) == 2
