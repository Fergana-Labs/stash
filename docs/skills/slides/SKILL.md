---
name: slides
description: How to build presentation slide decks as HTML pages. Covers the slide format, canvas dimensions, and recommended libraries.
when_to_use: When the user asks for slides, a slide deck, a presentation, a pitch, or a deck.
examples:
  - Turn what I saved this month into a slide deck.
  - Build a deck explaining this to someone who has never seen it.
  - Make a short pitch deck from my notes on this project.
version: "1"
---

# Building slide decks

A slide deck is a single HTML page with `html_layout: "fixed-aspect"` whose
`<body>` contains one `<section class="slide">` per slide.

## The canvas — 1920 × 1080 (16:9)

Every slide is a fixed **1920 × 1080 px** canvas with `overflow:hidden`.
Stay inside a **64 px safe-area margin** (working area 1792 × 952 px).
Nothing should scroll inside a slide; the viewer scales the canvas to fit
the viewport, and the exporter renders at native 1920×1080.

## Required structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Deck title</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6/css/all.min.css" rel="stylesheet">
  <style>
    /* Belt-and-suspenders — the viewer enforces these too. */
    section.slide {
      width: 1920px; height: 1080px;
      overflow: hidden; position: relative;
      box-sizing: border-box;
      padding: 64px;
    }
  </style>
</head>
<body>
  <section class="slide" data-type="cover">…</section>
  <section class="slide" data-type="content">…</section>
  <section class="slide" data-type="content">…</section>
  <section class="slide" data-type="final">…</section>
</body>
</html>
```

## Page types (`data-type`, optional but recommended)

- `cover` — title slide.
- `toc` — table of contents.
- `chapter` — section divider.
- `content` — regular content slide.
- `final` — thanks / Q&A / contact slide.

These let presenter view and future templates target slides by role.

## Typography

- Title text: **≥ 56 px**.
- Body text: **≥ 28 px**.
- Footnotes / captions: **≥ 20 px**.
- Use the system font stack or one CDN font (Inter, Geist).
  Avoid `@font-face` — it adds latency in export.

## Recommended libraries (all CDN-loadable)

| Need | Use |
|---|---|
| Charts | **Chart.js** for 1–2 charts per slide; **ECharts** for dashboards; D3 only when custom |
| Tables | Plain `<table>` + Tailwind classes. No DataTables. |
| Icons | **Font Awesome 6** (CDN) or **Lucide** |
| Code | **Shiki** (preferred, vector-clean) or **highlight.js** |
| Math | **KaTeX** with `auto-render` (never MathJax inside iframe) |
| Diagrams | **Mermaid** via CDN, render once on load |

Render charts at load time (inline `<script>` in the slide) so screenshot
exporters capture them. Don't rely on interactivity in PPTX/PDF.

## Anti-patterns

- More than ~40 words of body text per slide.
- Low contrast (white text on light backgrounds, etc.).
- `vh` / `vw` units — use `px`. The canvas is fixed-pixel.
- Images without `max-width: 100%` (they'll overflow).
- Fixed-positioned elements depending on viewport (`position: fixed`).
- Custom fonts loaded via `@font-face` from arbitrary URLs.
- Multiple `<section class="slide">` nested inside each other.

## Editing

Users can touch up text inline with the **Edit** button on the page.
Keep markup semantic — use `<h1>`, `<h2>`, `<p>`, `<ul>` rather than a
sea of `<div>`s — so the WYSIWYG editor's text selection and the
exporter's text-overlay extraction both work cleanly.

## Export

The PDF export is vector text. The PPTX and Google Slides exports embed
each slide as a high-DPI image plus an invisible text overlay so users
can select, copy, and search the text in PowerPoint / Keynote / Slides.
Don't ship interactive controls — they won't survive the export.
