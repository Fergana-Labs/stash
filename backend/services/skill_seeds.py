"""Default skill markdown seeded into every scope.

Each scope gets a set of `<skill>/SKILL.md` folders so agents can discover
them via `list_skills` / `read_skill`: `slides` (deck format), plus the
generate-output skills that turn saved material into documents —
`briefing`, `study-guide`, and `timeline`. Seeding is idempotent — if a
skill folder already has a SKILL.md we leave it alone (users may have
edited it).
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

# Env knob so the test suite can create blank scopes. Production
# leaves this unset; tests that need the seeded skills flip it off and
# call `seed_default_skills` directly.
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


BRIEFING_SKILL_MARKDOWN = """---
name: briefing
description: Synthesize a set of saved items (clips, X/Instagram saves, pages, source docs) into a one-page brief with links back to every source.
when_to_use: When the user asks for a briefing, a brief, a summary of what they've saved, or "catch me up" on a topic, folder, or collection.
version: "1"
---

# Writing a briefing

Turn a set of the user's saved material into one page they can read in two
minutes, with every claim one click from its source.

## Scope the source set

The user names the set: a topic ("my saves about agent memory"), a folder,
or explicit items. Gather it from their Stash — search for the topic, list
the folder, read each item. Read everything in the set before writing;
name anything you could not read in a "Not covered" line rather than
silently skipping it.

## Structure

1. **TL;DR** — at most three sentences.
2. **Key points, grouped by theme** — each point is a claim from the
   material with an inline link to the item it came from (the page, or the
   original post URL for an X/Instagram save). Never a claim without a link.
3. **Tensions and open questions** — where saved items disagree or leave a
   question hanging, say so explicitly and link both sides.
4. **Sources** — one line per item: title, where it came from, saved date.

## Rules

- Only the user's material. No outside knowledge presented as if it were
  in the set; if you add context, mark it "(context, not from your saves)".
- One page. Cut ruthlessly; the sources list carries the long tail.
- If you can write pages (e.g. via the `stash` CLI), save the brief as a
  page next to the material it covers; otherwise present it in the chat.
"""


STUDY_GUIDE_SKILL_MARKDOWN = """---
name: study-guide
description: Turn saved material into a study guide - key concepts, a reading order, and a question bank grounded in the user's own saves.
when_to_use: When the user wants to learn, study, review, or be quizzed on material they've saved on a topic.
version: "1"
---

# Writing a study guide

Turn the user's saved material on a topic into something they can actually
learn from, not just a summary.

## Scope the source set

Same as any synthesis: the user names a topic, folder, or items; gather
and read all of it from their Stash first. Name what you could not read.

## Structure

1. **Overview** — what this material collectively teaches, in a paragraph.
2. **Key concepts** — each with a one-sentence definition in your words and
   a link to the saved item that introduces it best.
3. **Reading order** — the saved items sequenced for learning (foundations
   first, applications later), one line on why each earns its place.
4. **Question bank** — 8-15 questions: recall questions ("what is X"),
   then application questions ("how would X handle Y"). Put answers with
   source links in a collapsed section or at the end, never inline.
5. **Review plan** — three checkpoints (a day, a week, a month out) with
   the two or three questions worth re-asking at each.

## Rules

- Ground every concept and answer in a linked saved item.
- Questions test the material, not trivia about it.
- If you can write pages, save the guide as a page; offer to quiz the user
  from its question bank in chat.
"""


TIMELINE_SKILL_MARKDOWN = """---
name: timeline
description: Build a chronological narrative from saved items - what happened when, how thinking evolved, with each entry linked to its source.
when_to_use: When the user asks how something evolved or unfolded, for a chronology, or for a timeline over their saved material.
version: "1"
---

# Writing a timeline

Order the user's saved material in time and narrate what changed.

## Scope and dates

Gather the set (topic, folder, or named items) and read it. Date each item
by the strongest signal available, in this order: a date stated in the
content itself (a post's date, an article's publication date), otherwise
the item's saved date — and say which you used when they differ enough to
matter.

## Structure

1. **Arc** — two or three sentences: where the story starts, where it ends.
2. **Entries, oldest first** — `date — what happened / what was claimed`,
   each linked to its saved item. Group same-week items when the timeline
   is dense.
3. **Turning points** — call out the two or three entries where the
   picture actually changed, and what changed.
4. **Gaps** — where the saved record goes quiet, say so; a missing month
   is information.

## Rules

- Every entry links to its source; never interpolate events that are not
  in the material.
- Keep entries to one or two lines — the links carry the detail.
- If you can write pages, save the timeline as a page next to its material.
"""


# folder name -> seeded SKILL.md body. Order is seed order.
DEFAULT_SKILLS: list[tuple[str, str]] = [
    (SLIDES_SKILL_FOLDER, SLIDES_SKILL_MARKDOWN),
    ("briefing", BRIEFING_SKILL_MARKDOWN),
    ("study-guide", STUDY_GUIDE_SKILL_MARKDOWN),
    ("timeline", TIMELINE_SKILL_MARKDOWN),
]


async def seed_default_skills(owner_user_id: UUID, creator_id: UUID) -> int:
    """Seed every default skill the scope doesn't already have. Returns how
    many SKILL.md pages were created. No-op when the env knob
    `STASH_DISABLE_DEFAULT_SKILL_SEEDS=1` is set (test mode)."""
    if os.environ.get(DISABLE_ENV_VAR) == "1":
        return 0
    created = 0
    for folder_name, markdown in DEFAULT_SKILLS:
        if await _seed_skill(owner_user_id, creator_id, folder_name, markdown):
            created += 1
    return created


async def _seed_skill(
    owner_user_id: UUID, creator_id: UUID, folder_name: str, markdown: str
) -> bool:
    """Create `<folder_name>/SKILL.md` in the scope if it doesn't exist.

    Returns True if the SKILL.md was created in this call, False if a
    SKILL.md was already present in any folder with that name (we treat
    that as "already seeded" and leave it alone — users may have edited it).
    """
    pool = get_pool()

    existing = await pool.fetchval(
        "SELECT p.id FROM pages p "
        "JOIN folders f ON f.id = p.folder_id "
        "WHERE f.owner_user_id = $1 AND lower(f.name) = $2 "
        "  AND p.name = $3 AND p.deleted_at IS NULL "
        "LIMIT 1",
        owner_user_id,
        folder_name,
        SKILL_MD_NAME,
    )
    if existing:
        return False

    folder_row = await pool.fetchrow(
        "SELECT id FROM folders WHERE owner_user_id = $1 AND lower(name) = $2 "
        "  AND parent_folder_id IS NULL LIMIT 1",
        owner_user_id,
        folder_name,
    )
    if folder_row:
        folder_id = folder_row["id"]
    else:
        folder = await files_tree_service.create_folder(
            owner_user_id=owner_user_id,
            name=folder_name,
            created_by=creator_id,
        )
        folder_id = folder["id"]

    await files_tree_service.create_page(
        owner_user_id=owner_user_id,
        name=SKILL_MD_NAME,
        created_by=creator_id,
        folder_id=folder_id,
        content=markdown,
        content_type="markdown",
    )
    logger.info("seeded %s skill for scope %s", folder_name, owner_user_id)
    return True
