# Design System — Stash landing (`www/`)

The landing page's brand system. It deliberately diverges from the cool, clinical,
sans-serif look that Supermemory and Hyperspell share — warm paper, a grotesque
display, and an elevated mono signature instead.

## Fonts
- **Display — Space Grotesk** (`--font-display`, weights 400–700). Headlines, the
  wordmark, card titles, big numbers. Also the product UI's display font, so the
  landing and app read as one brand. Max weight is **700** — never use `font-black`,
  it renders as faux-bold.
- **Body — Instrument Sans** (`--font-sans`). Paragraphs, ledes, UI text.
- **Mono — JetBrains Mono** (`--font-mono`), promoted to a *brand voice*: kickers,
  nav-adjacent labels, tags, captions, coordinate labels, terminal slabs.

## Color (warm paper palette — tokens in `globals.css`)
- Backgrounds: `--bg-base #FBFAF8`, `--bg-surface #F4F2EC` (alternating sections),
  `--bg-raised #EBE8DF`, `--bg-inverted #1A1714` (warm charcoal — terminal slabs only).
- Text: `--text-strong #1A1714`, `--text #44403A`, `--text-dim #6B655B`, `--text-muted #9A9389`.
- Brand orange `#F97316` (`--brand`) — used **rarely** (primary CTA, one highlighted
  word per heading, the terminal `›` prompt, the kicker brackets). If orange is on every
  element the accent dies.

## Signature moves
- **The mono kicker.** Every section opens with `[ SECTION.NAME ]` — the `.kicker`
  class (JetBrains Mono, uppercase, orange brackets via `::before`/`::after`). One
  ownable, repeatable label treatment. Author the label dotted/short: `How.it.works`.
- **Warm dot-field texture.** `<Texture>` paints `--dot-field` (a sparse, low-opacity
  dotted field) behind the hero, the closing CTA, and the OG image. Sparse and faded —
  **not** a stroke-heavy line grid.
- **Terminal slabs are the only dark surface.** Real `stash` CLI commands on
  `--bg-inverted`, mono, orange prompt. `<HeroTerminal>` types them out (the hero's
  centrepiece). Keep dark rare — it's what makes code feel canonical.
- **Asymmetric layouts.** Left-weighted hero, off-axis section headers. Avoid the
  centered, evenly-padded competitor template.

## Motion (CSS + tiny JS, no framer-motion; all gated on `prefers-reduced-motion`)
- `HeroTerminal` types real commands; `cursor-blink` for the caret.
- `.rise-in` — a short rise used on the hero kicker.
- `live-pulse` — the "live" status dot.

## CTA system
One pair everywhere: **`Sign up free →`** (orange, primary → `MANAGED_APP_URL`) and
**`Book a call`** (outlined, secondary → `/contact-sales`). Use the `<CtaPair>`
component. No other CTA labels ("Start free", "Talk to us", "Contact us" are retired).

## Rhythm
- Section vertical padding: 96–128px desktop (`py-24 md:py-32`).
- Max content width: 1200px. Section seams: `border-border-subtle`.

## Anti-patterns (do not ship)
- Cool/clinical white + neutral sans (that's the competitors).
- Overused serif + sans editorial pairing.
- Stroke-heavy line grids, node-network "memory graph" diagrams.
- Centered, evenly-padded competitor layout.
- `font-black`, or any font outside Space Grotesk / Instrument Sans / JetBrains Mono.
- "Unleash / Supercharge / Empower" copy; "Book a demo" as the primary CTA.
- Invented testimonials — the `TESTIMONIALS` array stays empty until we have real quotes.
