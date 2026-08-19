# Design System — Stash landing (`www/`)

The landing page's brand system. Warm paper, one accent, and restraint: the pages this
product gets compared to (Linear, Vercel, Resend, Modal, Cursor) win on space and type, not
on decoration.

## Fonts
- **Display — Chillax** (`--font-display`, weights 400–600). Headlines, the wordmark, card
  titles. A rounded geometric grotesque; it carries the warm half of the brand. Loaded from
  Fontshare via a stylesheet link in `layout.tsx`, since it is not on Google Fonts. Max weight
  is **600** — never `font-bold` or heavier, it renders as faux-bold.
- **Body — Supreme** (`--font-sans`). Paragraphs, ledes, UI text. Also from Fontshare.
- **Mono — IBM Plex Mono** (`--font-mono`) for labels, captions, code, and terminal slabs.
- **Serif — Instrument Serif** (`--font-serif`) for a single pull quote per page, and nothing
  else. If a page has two serif moments, one of them is wrong.

## Color (tokens in `globals.css`)
- Backgrounds: `--bg-base #F7F4EE` (warm paper), `--bg-surface #F1EDE5`, `--bg-raised #EBE6DC`,
  `--bg-inverted #16130F` (ink — code blocks and the docs announcement bar).
- Text: `--text-strong #16130F`, `--text #453F37`, `--text-dim #7C7469`, `--text-muted #A79E92`.
- Brand coral `#FF5A36` (`--brand`). **Two or three uses per screen, maximum**: one word in the
  headline, the primary button, and a single marker such as a bullet or an active nav item.
  White cards are `#FFFFFF` against the paper, which is what gives the page its depth.

## Signature moves
- **The artifact carries the page.** A real product capture or a real terminal transcript,
  never a diagram assembled from rounded rectangles and arrows.
- **Hairlines, not tinted sections.** Sections divide with `border-border-subtle` and vertical
  space. The one exception is a single ink section per page, used at most once.
- **Numbered hairline lists** for claims and principles: `01` in mono, a display-weight title,
  and one line of dim body. Used on the home page and on `/internal-agents`.
- **Asymmetric, left-weighted layouts** on the argument pages; the product page centres its
  hero and its code panel, and nothing else.

## Rhythm
- Section vertical padding: 64–112px (`py-16 md:py-28`).
- Max content width: 1180px. Docs run full-bleed with a 272px sidebar and a 232px TOC rail.
- Headline ≤ 9 words. Sub-copy ≤ 2 short lines, in `--text-dim`, never a paragraph.

## Pages
- `/` — the thesis. Four beliefs, two doors, a research index. No product tour.
- `/internal-agents` — the product page. Tabbed quickstart, import/refine/serve, sharing,
  ownership, research.
- `/external-agents` — the production-memory argument, written as documentation.
- `/blog`, `/contact-sales` — the same system, minus the product furniture.

## CTA system
`Sign up` (coral, primary) and `Book a call` (outlined). The header carries both plus a quiet
`Sign in`. On the argument pages the pair becomes `For internal agents` / `For external
agents`, which routes rather than converts.

## Anti-patterns (do not ship)
These are the tells that make a page read as machine-made. Each one was in a draft of this
redesign and was cut.
- All-caps eyebrows with wide letter-spacing above every section.
- Blurred colour blobs, glows, or any decorative gradient.
- The three-card grid, especially used more than once on a page.
- Status pills that state nothing (`● LIVE`, `STREAMING`), and chip rows under a CTA.
- Two accent colours competing across the page.
- A four-line hero paragraph.
- Invented testimonials or metrics. Benchmark claims need a citation before they ship.
- `font-black`, or any font outside Chillax / Supreme / IBM Plex Mono / Instrument Serif.
