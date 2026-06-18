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


DASHBOARD_SKILL_FOLDER = "build-on-stash"

DASHBOARD_SKILL_MARKDOWN = """---
name: build-on-stash
description: How to build a dashboard or vibe-coded UI on top of stash data — credentials, the supabase-style data API, realtime, and grounded AI.
when_to_use: When the user asks to build a dashboard, a UI, or an app on top of their stash tables / data.
version: "1"
---

# Building a UI on stash

Stash is the backend: your tables are the database, and you build any UI on top.
The data API is **PostgREST/supabase-js compatible**, so use code you already
know. Read the live schema from `/openapi.json` and `/llms.txt` before coding —
this guide is the stable how-to; those have the current tables and endpoints.

## 1. Credentials — pick by who the data is for

- **Your own private data** (a dashboard of *your* memory): mint a short-lived,
  read-only **dashboard token** — `POST /api/v1/dashboard-tokens {workspace_id}`
  → `{token, expires_at}`. Stash-hosted dashboards get one injected automatically.
- **Public / shared data** (everyone sees the same rows): the workspace owner
  creates a **publishable key** (`pk_…`) in settings and grants per-table
  read (or write) policies. Safe to embed in browser JS.

Never embed a long-lived `mc_` token in a browser.

## 2. Read & write — the data API (`/rest/v1/{table}`)

Point `supabase-js` at the stash URL, or use plain `fetch`. Tables are addressed
by name; columns by name.

```js
// Filter + select + order, supabase-js style:
GET /rest/v1/Sales?revenue=gt.1000&select=name,revenue&order=revenue.desc
// Insert / update / delete:
POST   /rest/v1/Sales            {"name": "Acme", "revenue": 5000}
PATCH  /rest/v1/Sales?id=eq.<id> {"revenue": 6000}
DELETE /rest/v1/Sales?id=eq.<id>
```

- Send the credential as `Authorization: Bearer <token>` or the `apikey` header.
- For an `mc_` token, also send `X-Stash-Workspace: <workspace_id>` (dashboard
  tokens and publishable keys already know their workspace).
- Row count comes back in the `Content-Range` response header.
- **Supported subset:** filters (`eq,neq,gt,gte,lt,lte,like,ilike,is.null`),
  `select`, single-column `order`, `limit`/`offset`. Embedded joins
  (`select=a,b(*)`), RPC, and `and/or/not` return **501** — don't use them.

## 3. Live updates — SSE (no websockets)

```js
const es = new EventSource(`/rest/v1/Sales/subscribe?access_token=${token}`);
es.onmessage = () => refetch();   // events are nudges: {type, row_id}
```

`EventSource` can't set headers, so the token goes in `?access_token=`.

## 4. Grounded AI (authenticated users only)

```js
// Chat with your data — Vercel AI SDK useChat works drop-in:
useChat({ api: `/ai/v1/${workspaceId}/chat` })
// Or raw retrieval:
POST /ai/v1/{workspace_id}/search {"query": "..."}
```

Publishable keys cannot call AI — broker it with a user token server-side.

## 5. Hosting

- **In stash:** save your single-file HTML dashboard as a Page with
  `html_layout: "app"`. It runs in a sandboxed iframe and, when you (the owner)
  view it, a `window.stash` client bound to your access is injected automatically
  — so it reads (and, with your owner/editor role, writes) your data with no key:

  ```html
  <script>
    const rows = await (await window.stash.rest(
      "Sales?select=Name,Revenue&order=Revenue.desc")).json();   // read
    await window.stash.rest("Sales", {                            // write
      method: "POST",
      body: JSON.stringify({ Name: "Acme", Revenue: 5000 }),
    });
  </script>
  ```

  A CSP egress-lock means an `app` page may call the stash API and load assets
  from common CDNs (jsdelivr, unpkg, cdnjs, tailwind, google fonts) — but cannot
  send data to any other origin. Use those CDNs for charting libs, etc.
- **Anywhere else:** deploy normally and point at the stash API with a `pk_` key
  (public/shared data) or a dashboard token.
"""


# The set of skills seeded into every new workspace. Add a one-liner here to
# ship another default skill — workspace creation loops over this list.
DEFAULT_SKILLS: list[tuple[str, str]] = [
    (SLIDES_SKILL_FOLDER, SLIDES_SKILL_MARKDOWN),
    (DASHBOARD_SKILL_FOLDER, DASHBOARD_SKILL_MARKDOWN),
]


async def _seed_skill(
    workspace_id: UUID, creator_id: UUID, folder_name: str, markdown: str
) -> bool:
    """Create `Skills/<folder>/SKILL.md` if a SKILL.md isn't already in that
    folder (we treat an existing one as already-seeded and leave user edits alone).
    """
    pool = get_pool()
    existing = await pool.fetchval(
        "SELECT p.id FROM pages p "
        "JOIN folders f ON f.id = p.folder_id "
        "WHERE f.workspace_id = $1 AND lower(f.name) = $2 "
        "  AND p.name = $3 AND p.deleted_at IS NULL "
        "LIMIT 1",
        workspace_id,
        folder_name,
        SKILL_MD_NAME,
    )
    if existing:
        return False

    folder_row = await pool.fetchrow(
        "SELECT id FROM folders WHERE workspace_id = $1 AND lower(name) = $2 "
        "  AND parent_folder_id IS NULL LIMIT 1",
        workspace_id,
        folder_name,
    )
    if folder_row:
        folder_id = folder_row["id"]
    else:
        folder = await files_tree_service.create_folder(
            workspace_id=workspace_id,
            name=folder_name,
            created_by=creator_id,
        )
        folder_id = folder["id"]

    await files_tree_service.create_page(
        workspace_id=workspace_id,
        name=SKILL_MD_NAME,
        created_by=creator_id,
        folder_id=folder_id,
        content=markdown,
        content_type="markdown",
    )
    logger.info("seeded %s skill for workspace %s", folder_name, workspace_id)
    return True


async def seed_default_skills(workspace_id: UUID, creator_id: UUID) -> None:
    """Seed every skill in DEFAULT_SKILLS into a new workspace (idempotent).

    No-op when `STASH_DISABLE_DEFAULT_SKILL_SEEDS=1` (test mode) — tests that
    need a seed call the seed helpers directly with the knob cleared.
    """
    if os.environ.get(DISABLE_ENV_VAR) == "1":
        return
    for folder_name, markdown in DEFAULT_SKILLS:
        await _seed_skill(workspace_id, creator_id, folder_name, markdown)


async def seed_slides_skill(workspace_id: UUID, creator_id: UUID) -> bool:
    """Seed just the slides skill. Kept as a direct entry point for tests."""
    if os.environ.get(DISABLE_ENV_VAR) == "1":
        return False
    return await _seed_skill(workspace_id, creator_id, SLIDES_SKILL_FOLDER, SLIDES_SKILL_MARKDOWN)
