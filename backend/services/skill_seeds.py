"""Default skill markdown seeded into every workspace.

Each workspace gets a `Skills/slides/SKILL.md` page so the ask-the-workspace
agent can discover it via `list_skills` / `read_skill` when the user asks
for a deck. Seeding is idempotent — if the folder already has a SKILL.md
we leave it alone (users may have edited it).
"""

from __future__ import annotations

import logging
import os
from uuid import UUID

from ..database import get_pool
from . import files_tree_service

logger = logging.getLogger(__name__)

SLIDES_SKILL_FOLDER = "slides"
SKILL_MD_NAME = "SKILL.md"

# Env knob so the test suite can create blank workspaces. Production
# leaves this unset; tests that need the seeded skill flip it off and
# call `seed_slides_skill` directly.
DISABLE_ENV_VAR = "STASH_DISABLE_DEFAULT_SKILL_SEEDS"


SLIDES_SKILL_MARKDOWN = """---
name: slides
description: How to build presentation slide decks as HTML pages. Covers the slide format, canvas dimensions, and recommended libraries.
when_to_use: When the user asks for slides, a slide deck, a presentation, a pitch, or a deck.
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
"""


async def seed_slides_skill(owner_user_id: UUID, creator_id: UUID) -> bool:
    """Create `Skills/slides/SKILL.md` in the workspace if it doesn't exist.

    Returns True if the SKILL.md was created in this call, False if a
    SKILL.md was already present in any folder named `slides` (we treat
    that as "already seeded" and leave it alone), or if the env knob
    `STASH_DISABLE_DEFAULT_SKILL_SEEDS=1` is set (test mode).
    """
    if os.environ.get(DISABLE_ENV_VAR) == "1":
        return False
    pool = get_pool()

    existing = await pool.fetchval(
        "SELECT p.id FROM pages p "
        "JOIN folders f ON f.id = p.folder_id "
        "WHERE f.owner_user_id = $1 AND lower(f.name) = $2 "
        "  AND p.name = $3 AND p.deleted_at IS NULL "
        "LIMIT 1",
        owner_user_id,
        SLIDES_SKILL_FOLDER,
        SKILL_MD_NAME,
    )
    if existing:
        return False

    folder_row = await pool.fetchrow(
        "SELECT id FROM folders WHERE owner_user_id = $1 AND lower(name) = $2 "
        "  AND parent_folder_id IS NULL LIMIT 1",
        owner_user_id,
        SLIDES_SKILL_FOLDER,
    )
    if folder_row:
        folder_id = folder_row["id"]
    else:
        folder = await files_tree_service.create_folder(
            owner_user_id=owner_user_id,
            name=SLIDES_SKILL_FOLDER,
            created_by=creator_id,
        )
        folder_id = folder["id"]

    await files_tree_service.create_page(
        owner_user_id=owner_user_id,
        name=SKILL_MD_NAME,
        created_by=creator_id,
        folder_id=folder_id,
        content=SLIDES_SKILL_MARKDOWN,
        content_type="markdown",
    )
    logger.info("seeded slides skill for workspace %s", owner_user_id)
    return True
