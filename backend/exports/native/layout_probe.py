"""HTML → list[SlideSpec] via Playwright.

The trick is to let Chromium do the layout work (Tailwind, Grid, Flex,
em-based sizing, etc.) and then read back computed positions + styles
for each element we want to emit as a PPTX shape. Per slide we open a
fresh page at 1920×1080 with the canvas-CSS injected (same CSS the
existing pptx exporter uses) and run one JavaScript block that walks
the DOM and returns the IR.

`probe(html)` is the only public entry; everything else is helpers.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from playwright.async_api import async_playwright

from ..constants import (
    EXPORT_DEVICE_SCALE_FACTOR,
    SLIDE_HEIGHT_PX,
    SLIDE_WIDTH_PX,
)
from ..pptx import _build_single_slide_html, _count_slides, _strip_body_state
from .spec import BBox, Paragraph, ShapeSpec, SlideSpec, TextRun

logger = logging.getLogger(__name__)


# JavaScript executed inside the Playwright page. Returns a JSON-able
# dict shaped like {bg_color, bg_complex, shapes: [...]}. We deliberately
# build the shape list in DOM order; the Python side reorders by z later.
#
# Why a single JS blob: each page.evaluate() roundtrip costs ~3-5 ms,
# and we want to capture O(elements) data per slide. Doing it once is
# orders of magnitude cheaper than per-element calls.
_PROBE_JS = r"""
() => {
  const slide = document.querySelector('body > section.slide:not([style*="display: none"])')
            || document.querySelector('body > section.slide');
  if (!slide) return { bg_color: null, bg_complex: false, shapes: [] };

  const slideRect = slide.getBoundingClientRect();

  // Element categorisation.
  const INLINE_TAGS = new Set([
    'STRONG', 'B', 'EM', 'I', 'U', 'A', 'SPAN', 'BR',
    'CODE', 'KBD', 'MARK', 'SUB', 'SUP', 'SMALL',
  ]);
  const TEXT_BLOCK_TAGS = new Set([
    'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
    'P', 'LI', 'TD', 'TH',
    'BLOCKQUOTE', 'FIGCAPTION', 'DT', 'DD',
    'BUTTON', 'LABEL', 'PRE',
  ]);
  // Block-level elements that often carry text directly (the agent's
  // skill encourages semantic tags, but real decks frequently inline
  // text in <div>).
  const CONTAINER_TAGS = new Set(['DIV', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER', 'NAV', 'MAIN', 'ASIDE']);

  const RASTER_TAGS = new Set(['CANVAS', 'SVG', 'IFRAME', 'VIDEO']);

  function relRect(el) {
    const r = el.getBoundingClientRect();
    return {
      x: r.left - slideRect.left,
      y: r.top - slideRect.top,
      w: r.width,
      h: r.height,
    };
  }

  function isVisible(el, style) {
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
      return false;
    }
    const r = el.getBoundingClientRect();
    return r.width >= 1 && r.height >= 1;
  }

  function colorToHex(s) {
    if (!s) return null;
    if (s === 'transparent' || s === 'rgba(0, 0, 0, 0)') return null;
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return s;
    const parts = m[1].split(',').map(p => parseFloat(p.trim()));
    if (parts.length >= 3) {
      const [r, g, b, a = 1] = parts;
      if (a < 0.05) return null;
      const h = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
      return '#' + h(r) + h(g) + h(b);
    }
    return s;
  }

  function bgIsComplex(style) {
    const img = style.backgroundImage;
    if (img && img !== 'none') return true;  // gradient or url()
    return false;
  }

  // Build a CSS selector that uniquely identifies an element relative
  // to the slide. We use it later if we need to raster-screenshot just
  // this element. nth-of-type chain is robust to anonymous nodes.
  function selectorFor(el) {
    const parts = [];
    let cur = el;
    while (cur && cur !== slide) {
      const tag = cur.tagName.toLowerCase();
      const parent = cur.parentElement;
      if (!parent) { parts.unshift(tag); break; }
      const siblings = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
      const idx = siblings.indexOf(cur) + 1;
      parts.unshift(`${tag}:nth-of-type(${idx})`);
      cur = parent;
    }
    return 'body > section.slide ' + parts.join(' > ');
  }

  // Detect if an element's only meaningful descendants are inline tags
  // and text nodes — i.e., it's a "text leaf" and we should capture it
  // as one TextSpec (potentially with multiple runs).
  function isTextLeaf(el) {
    for (const child of el.children) {
      if (!INLINE_TAGS.has(child.tagName)) return false;
    }
    return el.textContent.trim().length > 0;
  }

  // Walk inline children of a text leaf, accumulating TextRuns with
  // compounded formatting.
  function walkRuns(el, baseStyle, accum) {
    el.childNodes.forEach(node => {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent.replace(/\s+/g, ' ');
        if (!text || text === ' ') return;
        accum.push({
          text,
          bold: baseStyle.bold,
          italic: baseStyle.italic,
          underline: baseStyle.underline,
          font_size_px: baseStyle.font_size_px,
          font_family: baseStyle.font_family,
          color: baseStyle.color,
        });
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const child = node;
        if (child.tagName === 'BR') {
          accum.push({ text: '\n', bold: false, italic: false, underline: false,
                       font_size_px: baseStyle.font_size_px, font_family: baseStyle.font_family,
                       color: baseStyle.color });
          return;
        }
        const cs = getComputedStyle(child);
        const next = {
          bold: baseStyle.bold || parseInt(cs.fontWeight, 10) >= 600,
          italic: baseStyle.italic || cs.fontStyle === 'italic',
          underline: baseStyle.underline || cs.textDecorationLine.includes('underline'),
          font_size_px: parseFloat(cs.fontSize) || baseStyle.font_size_px,
          font_family: (cs.fontFamily || baseStyle.font_family).split(',')[0].replace(/['"]/g, '').trim(),
          color: colorToHex(cs.color) || baseStyle.color,
        };
        walkRuns(child, next, accum);
      }
    });
  }

  function textShape(el, style) {
    const runs = [];
    walkRuns(el, {
      bold: parseInt(style.fontWeight, 10) >= 600,
      italic: style.fontStyle === 'italic',
      underline: style.textDecorationLine.includes('underline'),
      font_size_px: parseFloat(style.fontSize) || 16,
      font_family: (style.fontFamily || '').split(',')[0].replace(/['"]/g, '').trim(),
      color: colorToHex(style.color) || '#000000',
    }, runs);
    if (!runs.length) return null;
    const para = {
      runs,
      align: ['left','center','right','justify'].includes(style.textAlign) ? style.textAlign : 'left',
      line_height: (() => {
        const lh = style.lineHeight;
        if (lh === 'normal' || !lh) return 1.2;
        const v = parseFloat(lh);
        const fs = parseFloat(style.fontSize) || 16;
        return v && fs ? v / fs : 1.2;
      })(),
    };
    return {
      kind: 'text',
      bbox: relRect(el),
      z: 0,
      paragraphs: [para],
      bg_color: null,
      padding_px: [
        parseFloat(style.paddingTop) || 0,
        parseFloat(style.paddingRight) || 0,
        parseFloat(style.paddingBottom) || 0,
        parseFloat(style.paddingLeft) || 0,
      ],
      src: null,
      cells: [],
      raster_selector: null,
      raster_reason: null,
    };
  }

  function imageShape(el) {
    return {
      kind: 'image',
      bbox: relRect(el),
      z: 0,
      paragraphs: [],
      bg_color: null,
      padding_px: [0, 0, 0, 0],
      src: el.getAttribute('src') || el.currentSrc || null,
      cells: [],
      raster_selector: null,
      raster_reason: null,
    };
  }

  function rasterShape(el, reason) {
    return {
      kind: 'raster',
      bbox: relRect(el),
      z: 0,
      paragraphs: [],
      bg_color: null,
      padding_px: [0, 0, 0, 0],
      src: null,
      cells: [],
      raster_selector: selectorFor(el),
      raster_reason: reason,
    };
  }

  function cardShape(el, style) {
    // A "card" is a block element with a coloured / bordered background
    // that contains text. Emit it as a coloured rectangle so the text
    // shapes inside sit on top of a real shape, not floating air.
    return {
      kind: 'text',
      bbox: relRect(el),
      z: -1,  // behind sibling text shapes
      paragraphs: [],
      bg_color: colorToHex(style.backgroundColor),
      padding_px: [
        parseFloat(style.paddingTop) || 0,
        parseFloat(style.paddingRight) || 0,
        parseFloat(style.paddingBottom) || 0,
        parseFloat(style.paddingLeft) || 0,
      ],
      src: null,
      cells: [],
      raster_selector: null,
      raster_reason: null,
    };
  }

  function tableShape(el) {
    const rows = [];
    for (const tr of el.querySelectorAll(':scope > thead > tr, :scope > tbody > tr, :scope > tr')) {
      const cells = [];
      for (const cell of tr.querySelectorAll(':scope > td, :scope > th')) {
        const cs = getComputedStyle(cell);
        const t = textShape(cell, cs);
        cells.push(t || {
          kind: 'text', bbox: relRect(cell), z: 0,
          paragraphs: [{ runs: [], align: 'left', line_height: 1.2 }],
          bg_color: colorToHex(cs.backgroundColor),
          padding_px: [0,0,0,0], src: null, cells: [],
          raster_selector: null, raster_reason: null,
        });
      }
      rows.push(cells);
    }
    return {
      kind: 'table',
      bbox: relRect(el),
      z: 0,
      paragraphs: [],
      bg_color: null,
      padding_px: [0, 0, 0, 0],
      src: null,
      cells: rows,
      raster_selector: null,
      raster_reason: null,
    };
  }

  const shapes = [];
  // Walk depth-first; once we emit a shape that fully owns its subtree
  // (text leaf, image, table, raster), skip descendants.
  function walk(el) {
    const style = getComputedStyle(el);
    if (!isVisible(el, style)) return;

    if (el.tagName === 'IMG') { shapes.push(imageShape(el)); return; }
    if (RASTER_TAGS.has(el.tagName)) { shapes.push(rasterShape(el, el.tagName.toLowerCase())); return; }
    if (el.dataset && el.dataset.exportRaster !== undefined) {
      shapes.push(rasterShape(el, 'data-export-raster')); return;
    }
    if (el.tagName === 'TABLE') { shapes.push(tableShape(el)); return; }

    const textBlock = TEXT_BLOCK_TAGS.has(el.tagName) || CONTAINER_TAGS.has(el.tagName);
    if (textBlock && isTextLeaf(el)) {
      const t = textShape(el, style);
      if (t) shapes.push(t);
      return;
    }

    // Card detection: container with a non-default background that
    // contains text shapes. Emit the background rectangle first, then
    // recurse.
    if (CONTAINER_TAGS.has(el.tagName)) {
      const bg = colorToHex(style.backgroundColor);
      const borderColor = colorToHex(style.borderTopColor);
      const borderWidth = parseFloat(style.borderTopWidth) || 0;
      if (bg || (borderWidth > 0 && borderColor)) {
        shapes.push(cardShape(el, style));
      }
    }

    for (const child of el.children) {
      walk(child);
    }
  }

  for (const child of slide.children) {
    walk(child);
  }

  const slideStyle = getComputedStyle(slide);
  return {
    bg_color: colorToHex(slideStyle.backgroundColor),
    bg_complex: bgIsComplex(slideStyle),
    shapes,
  };
}
"""


async def probe(html: str) -> list[SlideSpec]:
    """Render `html` slide-by-slide in a headless Chromium at 1920x1080
    and return a `SlideSpec` per `<section class="slide">`."""
    html = _strip_body_state(html or "")
    count = _count_slides(html)

    specs: list[SlideSpec] = []
    async with async_playwright() as p:
        # Same launch flags as the screenshot exporter — see pptx.py
        # for the rationale (`--no-sandbox`, `--disable-dev-shm-usage`).
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = await browser.new_context(
                viewport={"width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX},
                device_scale_factor=EXPORT_DEVICE_SCALE_FACTOR,
            )
            try:
                for i in range(count):
                    page = await context.new_page()
                    try:
                        slide_html = _build_single_slide_html(html, i)
                        await page.set_content(slide_html, wait_until="networkidle")
                        raw = await page.evaluate(_PROBE_JS)
                        specs.append(_raw_to_spec(i, raw))
                    finally:
                        await page.close()
            finally:
                await context.close()
        finally:
            await browser.close()
    return specs


def _raw_to_spec(index: int, raw: dict) -> SlideSpec:
    shapes_raw = raw.get("shapes") or []
    shapes = [_shape_from_raw(s) for s in shapes_raw]
    return SlideSpec(
        index=index,
        bg_color=raw.get("bg_color"),
        bg_raster_selector=("body > section.slide" if raw.get("bg_complex") else None),
        shapes=shapes,
    )


def _shape_from_raw(s: dict) -> ShapeSpec:
    bbox_raw = s["bbox"]
    bbox = BBox(x=bbox_raw["x"], y=bbox_raw["y"], w=bbox_raw["w"], h=bbox_raw["h"])
    paragraphs = [
        Paragraph(
            runs=[TextRun(**r) for r in (p.get("runs") or [])],
            align=p.get("align", "left"),
            line_height=p.get("line_height", 1.2),
        )
        for p in (s.get("paragraphs") or [])
    ]
    cells = [[_shape_from_raw(c) for c in row] for row in (s.get("cells") or [])]
    return ShapeSpec(
        kind=s["kind"],
        bbox=bbox,
        z=int(s.get("z", 0)),
        paragraphs=paragraphs,
        bg_color=s.get("bg_color"),
        padding_px=tuple(s.get("padding_px") or [0, 0, 0, 0]),
        src=s.get("src"),
        cells=cells,
        raster_selector=s.get("raster_selector"),
        raster_reason=s.get("raster_reason"),
    )


def spec_to_dict(spec: SlideSpec) -> dict:
    """JSON-snapshot helper for tests."""
    return asdict(spec)
