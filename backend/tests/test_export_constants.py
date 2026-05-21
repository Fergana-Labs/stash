"""Lock-in tests for the slide export canvas constants.

The PPTX, PDF, and Google Slides exporters all derive their dimensions
from `backend.exports.constants`. If these values drift, exports stop
matching the renderer's iframe (which targets the same 1920x1080 box).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.exports import constants, pptx

REPO_BACKEND = Path(__file__).resolve().parents[1]


def test_canvas_dimensions_consistent():
    assert constants.SLIDE_WIDTH_PX == 1920
    assert constants.SLIDE_HEIGHT_PX == 1080
    # 16:9 aspect ratio across all units.
    assert constants.SLIDE_WIDTH_PX / constants.SLIDE_HEIGHT_PX == pytest.approx(16 / 9)
    assert constants.SLIDE_WIDTH_INCHES / constants.SLIDE_HEIGHT_INCHES == pytest.approx(
        16 / 9, rel=1e-3
    )
    # EMU values match python-pptx's standard widescreen size.
    assert int(constants.SLIDE_WIDTH_EMU) == 12_192_000
    assert int(constants.SLIDE_HEIGHT_EMU) == 6_858_000


def test_device_scale_factor_is_meaningful():
    # 1x is the historical default; we explicitly want >=2 so exports
    # stay crisp on 4K displays / when zoomed in PowerPoint.
    assert constants.EXPORT_DEVICE_SCALE_FACTOR >= 2


def test_pptx_export_injects_canvas_css():
    """Slides whose HTML omits explicit dimensions still need to fill the
    1920x1080 canvas, or the screenshot ends up with whitespace below
    the content (and the resulting PPTX renders the slide as a thin
    band at the top of the page)."""
    html = '<!DOCTYPE html><html><body><section class="slide">x</section></body></html>'
    rendered = pptx._build_single_slide_html(html, 0)
    assert "section.slide" in rendered
    assert f"width: {constants.SLIDE_WIDTH_PX}px" in rendered
    assert f"height: {constants.SLIDE_HEIGHT_PX}px" in rendered


def test_strip_body_state_removes_viewer_pollution():
    """Legacy decks have <body style="zoom: …" contenteditable="true" ...>
    baked into their HTML from the WYSIWYG editor saving the live DOM.
    The export must strip those before rendering or the screenshot
    captures a shrunken body."""
    html = (
        "<!DOCTYPE html><html><body "
        'style="zoom: 0.4354; background: black;" '
        'contenteditable="true" spellcheck="true">'
        '<section class="slide">x</section></body></html>'
    )
    cleaned = pptx._strip_body_state(html)
    assert "zoom" not in cleaned, cleaned
    assert "contenteditable" not in cleaned, cleaned
    assert "spellcheck" not in cleaned, cleaned
    # Preserves other inline body styles.
    assert "background: black" in cleaned, cleaned
    assert "<section" in cleaned


def test_strip_body_state_handles_only_zoom_style():
    """If style=zoom was the only inline style, the entire style attr
    should disappear instead of leaving an empty one."""
    html = '<body style="zoom: 0.4;"><p>x</p></body>'
    cleaned = pptx._strip_body_state(html)
    assert 'style=""' not in cleaned
    assert "zoom" not in cleaned


def test_no_hardcoded_canvas_dims_in_exporters():
    """Catch a future regression where someone re-introduces 1920 or
    1080 as a literal in an exporter instead of importing the constant.
    Guards the consistency story in the PR plan."""
    for path in (REPO_BACKEND / "exports" / "pptx.py", REPO_BACKEND / "exports" / "pdf.py"):
        text = path.read_text()
        # Strip out comments so the audit doesn't flag explanatory text.
        no_comments = re.sub(r"#.*", "", text)
        assert "1920" not in no_comments, f"{path.name} hardcodes 1920 (use SLIDE_WIDTH_PX)"
        assert "1080" not in no_comments, f"{path.name} hardcodes 1080 (use SLIDE_HEIGHT_PX)"
