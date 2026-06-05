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
from ..html_canvas import build_single_slide_html, count_slides, strip_body_state
from ..playwright_network import abort_network_request
from .spec import (
    BBox,
    ChartDataset,
    ChartSpec,
    Gradient,
    GradientStop,
    Paragraph,
    ShapeSpec,
    SlideSpec,
    TextRun,
)

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
    // Clip to the slide canvas. Chart.js + responsive grids can size
    // elements far past the 1920x1080 slide; without clipping the
    // builder maps the full extent into PPTX coordinates and the
    // shape ends up extending below the visible page.
    const x = Math.max(0, r.left - slideRect.left);
    const y = Math.max(0, r.top - slideRect.top);
    const right = Math.min(slideRect.width, r.right - slideRect.left);
    const bottom = Math.min(slideRect.height, r.bottom - slideRect.top);
    return {
      x,
      y,
      w: Math.max(0, right - x),
      h: Math.max(0, bottom - y),
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
      // Use a low alpha cutoff so semi-transparent chip backgrounds
      // (rgba(255,255,255,0.06) style) still get captured as a colour.
      // We blend with white for the simple solid-fill case PPTX wants.
      if (a < 0.02) return null;
      const blend = (c) => Math.round(c * a + 255 * (1 - a));
      const h = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
      // For nearly-opaque fills, preserve original colour exactly.
      if (a >= 0.95) return '#' + h(r) + h(g) + h(b);
      return '#' + h(blend(r)) + h(blend(g)) + h(blend(b));
    }
    return s;
  }

  function bgIsComplex(style) {
    const img = style.backgroundImage;
    if (img && img !== 'none') return true;  // gradient or url()
    return false;
  }

  // Parse a CSS linear/radial gradient string into {type, angle, stops}.
  // Returns null if we can't recognise the syntax — caller falls back to raster.
  function parseGradient(bgImage) {
    if (!bgImage || bgImage === 'none') return null;
    // First gradient layer only — CSS allows stacked layers but Aspose's
    // gradient fill is single-stop-list, so we pick the most prominent.
    let type, body;
    if (bgImage.startsWith('linear-gradient(')) {
      type = 'linear'; body = bgImage.slice('linear-gradient('.length);
    } else if (bgImage.startsWith('radial-gradient(')) {
      type = 'radial'; body = bgImage.slice('radial-gradient('.length);
    } else {
      return null;
    }
    // Find the matching close paren, respecting nested rgb(...) etc.
    let depth = 1, end = -1;
    for (let i = 0; i < body.length; i++) {
      const c = body[i];
      if (c === '(') depth++;
      else if (c === ')') { depth--; if (depth === 0) { end = i; break; } }
    }
    if (end === -1) return null;
    const raw = body.slice(0, end);

    // Split on commas at depth 0 (avoid splitting inside rgba(...)).
    const parts = [];
    depth = 0;
    let buf = '';
    for (const ch of raw) {
      if (ch === '(') depth++;
      if (ch === ')') depth--;
      if (ch === ',' && depth === 0) { parts.push(buf.trim()); buf = ''; }
      else buf += ch;
    }
    if (buf.trim()) parts.push(buf.trim());

    let angle = 180;  // CSS default for linear is "to bottom" = 180deg
    let first = 0;
    if (type === 'linear' && parts.length) {
      const angleMatch = parts[0].match(/^(-?\d+(?:\.\d+)?)deg$/);
      const toMatch = parts[0].match(/^to\s+(top|bottom|left|right)(?:\s+(top|bottom|left|right))?$/);
      if (angleMatch) { angle = parseFloat(angleMatch[1]); first = 1; }
      else if (toMatch) {
        const dirs = {top: 0, right: 90, bottom: 180, left: 270};
        angle = dirs[toMatch[1]] ?? 180;
        first = 1;
      }
    } else if (type === 'radial' && parts.length) {
      // Skip the shape/position prefix if present ("circle at center", "ellipse 30% 50%", etc).
      if (!/rgba?\(|^#|^[a-z]+$/i.test(parts[0])) first = 1;
    }

    const stops = [];
    const total = parts.length - first;
    parts.slice(first).forEach((p, i) => {
      // Each stop: "<color> [<offset%>]"
      const m = p.match(/^(rgba?\([^)]+\)|#[0-9a-f]+|[a-z]+)(?:\s+(-?\d+(?:\.\d+)?)(%|px)?)?$/i);
      if (!m) return;
      const color = colorToHex(m[1]) || m[1];
      let offset;
      if (m[2] && m[3] === '%') offset = parseFloat(m[2]) / 100;
      else if (m[2] === undefined) offset = total > 1 ? i / (total - 1) : 0;
      else offset = parseFloat(m[2]) / 100;
      stops.push({ offset: Math.max(0, Math.min(1, offset)), color });
    });
    if (stops.length < 2) return null;
    return { type, angle, stops };
  }

  // Extract Chart.js config from a canvas element. Requires Chart.js to
  // be loaded and rendered; returns null for vanilla <canvas> elements.
  function extractChartJs(el) {
    try {
      // Chart.getChart was added in Chart.js v3+. Earlier versions exposed
      // Chart.instances; we don't support those.
      if (typeof window.Chart !== 'function' || typeof window.Chart.getChart !== 'function') return null;
      const inst = window.Chart.getChart(el);
      if (!inst) return null;
      const cfg = inst.config;
      let type = cfg.type;
      // Map Chart.js types to PPTX-supported families.
      const typeMap = { bar: 'bar', line: 'line', pie: 'pie', doughnut: 'doughnut', area: 'area' };
      const datasets = (cfg.data.datasets || []);
      // Promote line → area when any dataset opts into fill:true. Chart.js
      // renders that as a filled area, and Aspose only matches by chart kind.
      if (type === 'line' && datasets.some(d => d.fill === true || (d.fill && d.fill !== false && d.fill !== 'none'))) {
        type = 'area';
      }
      const mapped = typeMap[type];
      if (!mapped) return null;
      const labels = (cfg.data.labels || []).map(String);
      const ds = datasets.map(d => ({
        label: String(d.label || ''),
        data: (d.data || []).map(v => Number(v) || 0),
        color: colorToHex(
          typeof d.borderColor === 'string' ? d.borderColor
          : typeof d.backgroundColor === 'string' ? d.backgroundColor
          : null
        ),
        line_width_px: typeof d.borderWidth === 'number' ? d.borderWidth : null,
        point_radius_px: typeof d.pointRadius === 'number' ? d.pointRadius : null,
      }));
      const title = (cfg.options && cfg.options.plugins && cfg.options.plugins.title && cfg.options.plugins.title.text) || '';
      // Axis font: Chart.js defaults.font.size = 12. Per-scale override
      // wins. We sample the X-axis since it's the most visually obvious.
      const defaultFont = (window.Chart.defaults && window.Chart.defaults.font && window.Chart.defaults.font.size) || 12;
      const xScale = cfg.options && cfg.options.scales && (cfg.options.scales.x || cfg.options.scales.xAxes && cfg.options.scales.xAxes[0]);
      const tickFont = xScale && xScale.ticks && xScale.ticks.font && xScale.ticks.font.size;
      const axisFontSize = typeof tickFont === 'number' ? tickFont : defaultFont;
      return { type: mapped, labels, datasets: ds, title: String(title || ''), axis_font_size_px: axisFontSize };
    } catch (e) { return null; }
  }

  // Pull SVG bytes either from an <img src="data:image/svg+xml,..."> or
  // an inline <svg>. Returned as raw markup so Aspose can ingest it.
  function extractSvg(el) {
    if (el.tagName === 'IMG') {
      const src = el.getAttribute('src') || '';
      if (!src.startsWith('data:image/svg+xml')) return null;
      try {
        if (src.includes(';base64,')) {
          return atob(src.split(';base64,')[1]);
        }
        return decodeURIComponent(src.split(',')[1] || '');
      } catch (e) { return null; }
    }
    if (el.tagName === 'SVG') return el.outerHTML;
    return null;
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
      // An inline child with its own background is a chip / pill — emit it
      // as its own shape later, not absorbed into the parent paragraph.
      if (colorToHex(getComputedStyle(child).backgroundColor)) return false;
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
    // If the text-leaf itself has a non-default background (chip / pill /
    // labeled callout), bake it into the shape so the builder emits a real
    // coloured rectangle with the text inside instead of a transparent
    // textbox over the slide bg.
    const ownBg = colorToHex(style.backgroundColor);
    return {
      kind: 'text',
      bbox: relRect(el),
      z: 0,
      paragraphs: [para],
      bg_color: ownBg,
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
      svg: null,
      chart: null,
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
      svg: null,
      chart: null,
    };
  }

  function svgShape(el, svgMarkup) {
    return {
      kind: 'svg',
      bbox: relRect(el),
      z: 0,
      paragraphs: [],
      bg_color: null,
      padding_px: [0, 0, 0, 0],
      src: null,
      cells: [],
      // raster_selector is kept populated so the python-pptx builder
      // (which doesn't know svg/chart kinds) can still fall back to
      // a screenshot. The aspose builder ignores it when svg/chart
      // is present.
      raster_selector: selectorFor(el),
      raster_reason: 'svg',
      svg: svgMarkup,
      chart: null,
    };
  }

  function chartShape(el, chartCfg) {
    return {
      kind: 'chart',
      bbox: relRect(el),
      z: 0,
      paragraphs: [],
      bg_color: null,
      padding_px: [0, 0, 0, 0],
      src: null,
      cells: [],
      raster_selector: selectorFor(el),
      raster_reason: 'chart',
      svg: null,
      chart: chartCfg,
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
      svg: null,
      chart: null,
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
      svg: null,
      chart: null,
    };
  }

  function tableShape(el) {
    const rows = [];
    let colWidths = [];
    let borderColor = null;
    let borderWidth = 0;
    const tableRect = el.getBoundingClientRect();
    let isFirstRow = true;
    for (const tr of el.querySelectorAll(':scope > thead > tr, :scope > tbody > tr, :scope > tr')) {
      const cells = [];
      for (const cell of tr.querySelectorAll(':scope > td, :scope > th')) {
        const cs = getComputedStyle(cell);
        if (isFirstRow) {
          colWidths.push(cell.getBoundingClientRect().width);
          // Sample border once — assume table is uniform per HTML's
          // border-collapse model.
          const bw = parseFloat(cs.borderBottomWidth) || 0;
          if (bw > borderWidth) {
            borderWidth = bw;
            borderColor = colorToHex(cs.borderBottomColor);
          }
        }
        const t = textShape(cell, cs);
        cells.push(t || {
          kind: 'text', bbox: relRect(cell), z: 0,
          paragraphs: [{ runs: [], align: 'left', line_height: 1.2 }],
          bg_color: colorToHex(cs.backgroundColor),
          padding_px: [0,0,0,0], src: null, cells: [],
          raster_selector: null, raster_reason: null,
          svg: null, chart: null,
        });
      }
      rows.push(cells);
      isFirstRow = false;
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
      svg: null,
      chart: null,
      col_widths_px: colWidths,
      border_color: borderColor,
      border_width_px: borderWidth,
    };
  }

  const shapes = [];
  // Walk depth-first; once we emit a shape that fully owns its subtree
  // (text leaf, image, table, raster), skip descendants.
  function walk(el) {
    const style = getComputedStyle(el);
    if (!isVisible(el, style)) return;

    if (el.tagName === 'IMG') {
      // Inline-SVG data URIs can be passed through as vector — they're
      // editable in PowerPoint and stay crisp at any zoom.
      const svg = extractSvg(el);
      if (svg) { shapes.push(svgShape(el, svg)); return; }
      shapes.push(imageShape(el)); return;
    }
    if (el.tagName === 'CANVAS') {
      const chartCfg = extractChartJs(el);
      if (chartCfg) { shapes.push(chartShape(el, chartCfg)); return; }
      shapes.push(rasterShape(el, 'canvas')); return;
    }
    if (el.tagName === 'SVG') {
      shapes.push(svgShape(el, el.outerHTML)); return;
    }
    if (RASTER_TAGS.has(el.tagName)) { shapes.push(rasterShape(el, el.tagName.toLowerCase())); return; }
    if (el.dataset && el.dataset.exportRaster !== undefined) {
      shapes.push(rasterShape(el, 'data-export-raster')); return;
    }
    if (el.tagName === 'TABLE') { shapes.push(tableShape(el)); return; }

    // Promote an inline element to a standalone text shape when it has its
    // own background — that's how the slides skill (and most decks) build
    // chips and pills: <span class="chip" style="background:..."> ... </span>.
    // Without this, the chip text gets absorbed into the parent paragraph
    // and the background is lost entirely.
    const ownBgHex = colorToHex(style.backgroundColor);
    const looksLikeChip = (
      INLINE_TAGS.has(el.tagName) &&
      ownBgHex &&
      el.textContent.trim().length > 0 &&
      isTextLeaf(el)
    );

    const textBlock = TEXT_BLOCK_TAGS.has(el.tagName) || CONTAINER_TAGS.has(el.tagName);
    if ((textBlock && isTextLeaf(el)) || looksLikeChip) {
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
  const bgGradient = parseGradient(slideStyle.backgroundImage);
  return {
    bg_color: colorToHex(slideStyle.backgroundColor),
    bg_complex: bgIsComplex(slideStyle),
    bg_gradient: bgGradient,
    shapes,
  };
}
"""


async def probe(html: str) -> list[SlideSpec]:
    """Render `html` slide-by-slide in a headless Chromium at 1920x1080
    and return a `SlideSpec` per `<section class="slide">`."""
    html = strip_body_state(html or "")
    count = count_slides(html)

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
                await context.route("**/*", abort_network_request)
                for i in range(count):
                    page = await context.new_page()
                    try:
                        slide_html = build_single_slide_html(html, i)
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

    bg_gradient = _gradient_from_raw(raw.get("bg_gradient"))
    # Keep the raster selector populated whenever the background is non-trivial.
    # python-pptx has no native gradient path, so it falls back to raster.
    # aspose_builder ignores bg_raster_selector when bg_gradient is set.
    bg_raster = None
    if raw.get("bg_complex"):
        # `_build_single_slide_html` sets display:none on every section
        # except the active one. Without the :not() filter Playwright's
        # screenshot retries against the first match (slide 0, hidden)
        # until the 30 s timeout.
        bg_raster = 'body > section.slide:not([style*="display: none"])'

    return SlideSpec(
        index=index,
        bg_color=raw.get("bg_color"),
        bg_gradient=bg_gradient,
        bg_raster_selector=bg_raster,
        shapes=shapes,
    )


def _gradient_from_raw(raw: dict | None) -> Gradient | None:
    if not raw:
        return None
    stops = [
        GradientStop(offset=float(s.get("offset", 0.0)), color=str(s.get("color", "#000000")))
        for s in (raw.get("stops") or [])
    ]
    if len(stops) < 2:
        return None
    return Gradient(
        type=raw.get("type") or "linear",
        angle=float(raw.get("angle") or 0.0),
        stops=stops,
    )


def _chart_from_raw(raw: dict | None) -> ChartSpec | None:
    if not raw:
        return None
    return ChartSpec(
        type=raw.get("type") or "bar",
        labels=[str(x) for x in (raw.get("labels") or [])],
        datasets=[
            ChartDataset(
                label=str(d.get("label") or ""),
                data=[float(v) for v in (d.get("data") or [])],
                color=d.get("color"),
                line_width_px=(
                    float(d["line_width_px"]) if d.get("line_width_px") is not None else None
                ),
                point_radius_px=(
                    float(d["point_radius_px"]) if d.get("point_radius_px") is not None else None
                ),
            )
            for d in (raw.get("datasets") or [])
        ],
        title=str(raw.get("title") or ""),
        axis_font_size_px=(
            float(raw["axis_font_size_px"]) if raw.get("axis_font_size_px") is not None else None
        ),
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
        col_widths_px=[float(w) for w in (s.get("col_widths_px") or [])],
        border_color=s.get("border_color"),
        border_width_px=float(s.get("border_width_px") or 0.0),
        raster_selector=s.get("raster_selector"),
        raster_reason=s.get("raster_reason"),
        svg=s.get("svg"),
        chart=_chart_from_raw(s.get("chart")),
    )


def spec_to_dict(spec: SlideSpec) -> dict:
    """JSON-snapshot helper for tests."""
    return asdict(spec)
