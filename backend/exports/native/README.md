# `backend/exports/native/` — native-shape export sandbox

Experimental PPTX (and, via Drive conversion, Google Slides) exporter
that emits real text frames, real pictures, and real tables rather than
full-bleed screenshots. The goal: open the export in PowerPoint /
Keynote / Slides and have **selectable, editable text** at the right
positions.

Nothing here is registered as a celery task or exposed through the API
yet. The driver is the CLI in this folder + the tests. We iterate until
the output is genuinely better than the screenshot pipeline, then wire
it in behind a feature flag.

## Layout

| File | Role |
|---|---|
| `spec.py` | `SlideSpec` / `ShapeSpec` / `TextRun` dataclasses — the IR between probe and builder |
| `layout_probe.py` | Playwright @ 1920×1080 → walks the DOM → returns `list[SlideSpec]` |
| `image_fetch.py` | `data:` URI / R2 / external URL → bytes, with per-run in-memory cache |
| `hybrid_raster.py` | Playwright element screenshot for backgrounds, `<canvas>`, `<svg>` |
| `pptx_builder.py` | `list[SlideSpec]` → PPTX bytes via `python-pptx` native shapes |
| `cli.py` | `python -m backend.exports.native.cli <page_id>` driver |
| `diff.py` | `/tmp/diff-<page_id>.html` side-by-side: original render \| screenshot \| native |
| `fixtures/sample_decks/` | Captured `content_html` for regression — checked in |
| `tests/` | unit + snapshot tests; no Playwright in CI (skipped unless `PLAYWRIGHT_AVAILABLE=1`) |

## Why a probe + builder, not pure HTML→XML

CSS layout is hard; Playwright already implements it. Per slide we open
a Chromium page at exactly 1920×1080 with the canvas-enforcing CSS
injected, then evaluate one JavaScript block that walks the live DOM
and returns `getBoundingClientRect()` + `getComputedStyle()` for every
relevant element. We turn those into `ShapeSpec`s and feed them to
`python-pptx`. The browser does the layout; we do the translation.

## Why hybrid raster

A few elements don't translate to PPTX shapes cleanly (or at all):

- Backgrounds with gradients, patterns, or `background-image`.
- `<canvas>` (Chart.js / ECharts).
- `<svg>` (Mermaid, custom illustrations).
- Anything tagged `data-export-raster` — escape hatch for designs that
  the agent author decides shouldn't translate.

For these we screenshot just that element with Playwright's
`elementHandle.screenshot()` and embed the PNG. Everything else stays
native. Hybrid > all-or-nothing.

## Promotion path

When the diff report against the `fixtures/sample_decks/` corpus shows
parity-or-better on PowerPoint and Google Slides:

1. Add a `format=pptx-native` value (or env-flag the existing task) in
   `backend/exports/pptx.py` that delegates to `pptx_builder.build()`.
2. Keep `format=pptx` (screenshot) as a fallback for one release.
3. Once stable, swap the default and delete the screenshot path.

## Local run

```
python -m backend.exports.native.cli <page_id> --out /tmp/native.pptx
python -m backend.exports.native.diff <page_id>   # writes /tmp/diff-<page_id>.html
```

Requires `DATABASE_URL` in env (same as the rest of the backend) and
Playwright's chromium installed (`playwright install chromium`).
