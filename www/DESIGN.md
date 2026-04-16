# Design System — Stash landing (`www/`)

Extends the main Stash design system at `/DESIGN.md`. Only the landing-specific deltas live here.

## Inherited (do not override)

- Fonts: Satoshi (display), Instrument Sans (body), JetBrains Mono (code)
- Palette: warm slates, orange `#F97316` accent, violet for agents, blue for humans
- Base unit: 4px; radii sm/md/lg/full
- Light mode default

## Landing extensions

### Type scale
- Hero headline: Satoshi 900, clamp(48px, 6vw, 88px), -0.04em, line-height 1.0
- Section heading: Satoshi 700, 36–40px, -0.02em
- Lede / subhead: Instrument Sans 400, 20–22px, line-height 1.45, `color: slate-500`
- Eyebrow label: JetBrains Mono 500, 11px, uppercase, 0.12em tracking, `color: slate-400`

### Rhythm
- Section vertical padding: 120px desktop, 72px mobile
- Max content width: 1120px (matches product); hero allowed to reach 1200px
- Gap within a section: 32–48px

### Signature moves
- **Dark terminal slab on light page.** The install block is the only dark surface on the page. `#0F172A` background, JetBrains Mono, orange `$` prompt. This makes code feel canonical; the rest of the page is light.
- **Orange is rare.** Primary CTA button + one highlighted word in the hero + one underline. That's it. If orange shows up on every section the accent dies.
- **Satoshi does the work.** No decorative shapes, no gradients, no icon-in-circle feature grids. The hero's geometric sans is the personality.

### Anti-patterns (do not ship)
- Purple/violet gradients
- Floating orbs, mesh blobs, grain overlays
- Three-column icon grids with colored circles
- Centered-everything layouts
- "Unleash / Supercharge / Empower" copy
- Any font not in the inherited stack
