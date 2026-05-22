"""HTML canvas helpers shared between the exporter and the layout probe.

Slide decks live as a single HTML document with multiple
`<section class="slide">`s. The exporter and the probe both need to:
- count the sections,
- strip the viewer's bootstrap attributes (`zoom`, `contenteditable`,
  `spellcheck`) the WYSIWYG saves into the live DOM,
- render exactly one slide at a time inside a 1920x1080 canvas.

Lives outside `pptx.py` so the native exporter and its sub-modules can
import it without pulling in the Celery task / S3 client surface (which
would create a circular import through `aspose_builder` → `hybrid_raster`
→ `pptx`).
"""

from __future__ import annotations

import re

from .constants import SLIDE_HEIGHT_PX, SLIDE_WIDTH_PX

SECTION_RE = re.compile(
    r"<section\b[^>]*\bclass\s*=\s*[\"'][^\"']*\bslide\b[^\"']*[\"'][^>]*>",
    re.IGNORECASE,
)

# Mirrors the canvas-enforcing CSS the in-app slide viewer injects (see
# injectSlideDeckBootstrap in HtmlPageView.tsx). Without it, an agent that
# omits explicit dimensions ends up with a section sized to its content
# height — and the probe captures shapes in a body shorter than the slide.
_CANVAS_CSS = f"""
  html, body {{ margin: 0; padding: 0; }}
  body > section.slide {{
    width: {SLIDE_WIDTH_PX}px;
    height: {SLIDE_HEIGHT_PX}px;
    overflow: hidden;
    position: relative;
    box-sizing: border-box;
    display: block;
  }}
"""


def count_slides(html: str) -> int:
    return max(1, len(SECTION_RE.findall(html or "")))


def strip_body_state(html: str) -> str:
    """Remove inline body attributes the viewer bootstrap leaves behind:
    `style="zoom: …"` from applyCanvasZoom, and `contenteditable` /
    `spellcheck` from the WYSIWYG. Legacy pages saved before this strip
    was added still have these baked in — without removing them, the
    probe renders the body shrunk to a fraction of the slide width,
    leaving the rest as body bg."""
    return re.sub(
        r"<body([^>]*)>",
        lambda m: "<body" + _clean_body_attrs(m.group(1)) + ">",
        html,
        count=1,
        flags=re.I,
    )


def _clean_body_attrs(attrs: str) -> str:
    # Drop contenteditable + spellcheck attributes entirely.
    attrs = re.sub(r"\s*contenteditable\s*=\s*\"[^\"]*\"", "", attrs, flags=re.I)
    attrs = re.sub(r"\s*spellcheck\s*=\s*\"[^\"]*\"", "", attrs, flags=re.I)

    # Drop `zoom: …;` from inline style. If style becomes empty, drop the attr.
    def _strip_zoom(m: re.Match) -> str:
        css = re.sub(r"\s*zoom\s*:\s*[^;\"]*;?", "", m.group(1), flags=re.I).strip()
        return "" if not css else f' style="{css}"'

    attrs = re.sub(r"\s*style\s*=\s*\"([^\"]*)\"", _strip_zoom, attrs, count=1, flags=re.I)
    return attrs


def build_single_slide_html(source_html: str, slide_index: int) -> str:
    """Return HTML showing only the Nth <section class="slide"> with the
    canvas-enforcing CSS injected so the section fills the slide canvas
    even when the agent's HTML omitted explicit dimensions."""
    css = f"<style>{_CANVAS_CSS}</style>"
    script = (
        "<script>(function(){var s=document.querySelectorAll('body > section.slide');"
        + f"var i={slide_index};"
        + "for(var k=0;k<s.length;k++){s[k].style.display=(k===i)?'':'none';}})();</script>"
    )
    html = strip_body_state(source_html)
    if re.search(r"</head\s*>", html, flags=re.I):
        html = re.sub(r"</head\s*>", css + "</head>", html, count=1, flags=re.I)
    else:
        html = css + html
    if re.search(r"</body\s*>", html, flags=re.I):
        return re.sub(r"</body\s*>", script + "</body>", html, count=1, flags=re.I)
    return html + script
