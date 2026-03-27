# Design System — Boozle

## Product Context
- **What this is:** Real-time workspace platform where AI agents and humans collaborate as peers — chats, notebooks, and memory stores
- **Who it's for:** Developers building with AI agents, technical teams running multi-agent workflows
- **Space/industry:** AI collaboration tools, developer platforms (peers: Cursor, Linear, CrewAI, Notion)
- **Project type:** Web app (Next.js 16 + Tailwind 4 frontend, Python/FastAPI backend)

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian — function-first, data-dense, monospace accents
- **Decoration level:** Minimal — typography and color do the work, no gradients or glow effects
- **Mood:** Serious developer tool with warmth and personality. Structure says "capable"; orange accent says "this is fun to use." The name "Boozle" is playful — the design leans into that.
- **Reference sites:** Cursor (cursor.com), Linear (linear.app), Vercel (vercel.com), Raycast (raycast.com)

## Typography
- **Display/Hero:** Satoshi (900, 700, 500) — geometric sans with distinctive letterforms, gives Boozle its own identity
- **Body:** Instrument Sans (400, 500, 600, 700) — clean, modern, excellent readability at small sizes
- **UI/Labels:** Instrument Sans (500, 600) — same as body for consistency
- **Data/Tables:** JetBrains Mono (400, 500) — supports tabular-nums, developer standard
- **Code:** JetBrains Mono (400)
- **Loading:** Satoshi via Fontshare CDN (`https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap`), Instrument Sans + JetBrains Mono via Google Fonts
- **Scale:**
  - Hero: 48px / Black 900 / -0.03em tracking
  - Page title: 32px / Bold 700 / -0.02em tracking
  - Section heading: 24px / Bold 700 / -0.01em tracking
  - Card title: 20px / SemiBold 600
  - Body: 15px / Regular 400 / 1.65 line-height
  - UI labels: 13px / Medium 500
  - System labels (mono): 11px / uppercase / 0.05em tracking

## Color
- **Approach:** Restrained — one bold accent + semantic agent/human colors + warm slates
- **Primary:** #F97316 (warm orange) — brand color, CTAs, active states, focus rings. Bold and warm. Hover: #EA580C. Muted: rgba(249, 115, 22, 0.15)
- **Agent semantic:** #8B5CF6 (violet) — avatars, tags, borders for AI agent elements. Muted: rgba(139, 92, 246, 0.15)
- **Human semantic:** #3B82F6 (blue) — avatars, tags, borders for human elements. Muted: rgba(59, 130, 246, 0.15)
- **Neutrals (warm slates):**
  - 50: #F8FAFC
  - 100: #F1F5F9
  - 300: #CBD5E1
  - 400: #94A3B8
  - 500: #64748B
  - 700: #334155
  - 800: #1E293B
  - 900: #0F172A
- **Semantic:**
  - Success: #22C55E / muted: rgba(34, 197, 94, 0.12)
  - Warning: #EAB308 / muted: rgba(234, 179, 8, 0.12)
  - Error: #EF4444 / muted: rgba(239, 68, 68, 0.12)
  - Info: #3B82F6 / muted: rgba(59, 130, 246, 0.12)
- **Light mode (default):** Base #FFFFFF, Surface #F8FAFC, Elevated #F1F5F9, Border #E2E8F0
- **Dark mode:** Base #1E293B, Surface #273548, Elevated #334155, Border #3E4E63. Lighter than typical dark dev tools — warm mid-slate, not deep navy.

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable — enough breathing room for readability, tight enough for data-dense views
- **Scale:** 2xs(2) xs(4) sm(8) md(16) lg(24) xl(32) 2xl(48) 3xl(64)

## Layout
- **Approach:** Grid-disciplined — sidebar + content for workspace views, strict alignment
- **Grid:** Sidebar (220px fixed) + flexible content area. Max content width 680px for notebooks/readable content, full-width for data-dense views (memory stores)
- **Max content width:** 1120px for page container
- **Border radius:** sm:4px (inputs, tags), md:8px (buttons, cards), lg:12px (containers, mockups), full:9999px (badges, avatars, pills)

## Motion
- **Approach:** Minimal-functional — only transitions that aid comprehension
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out)
- **Duration:** micro(50-100ms) hover(150ms) slide(200ms) fade(150ms)
- **No decorative animation.** This is a workspace, not a marketing site.

## Agent/Human Visual System
- Agents are always marked with **violet** (#8B5CF6) — avatars, type tags, collaboration cursors, memory store source dots
- Humans are always marked with **blue** (#3B82F6) — same treatment
- The brand **orange** (#F97316) is the platform color — sits above both, used for CTAs, active states, and brand elements
- Type tags: monospace, uppercase, 10px, colored background + text (e.g., `agent` tag in violet, `human` tag in blue)

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-26 | Initial design system created | Created by /design-consultation based on competitive research of Cursor, Linear, Vercel, Raycast, CrewAI |
| 2026-03-26 | Orange #F97316 as primary accent | No AI/agent platform uses orange — distinctive, warm, matches playful "Boozle" name |
| 2026-03-26 | Satoshi as display font | Geometric sans with personality — gives Boozle its own typographic identity vs. generic Inter/Geist |
| 2026-03-26 | Light mode as default, lighter dark mode | User preference for lighter backgrounds. Dark mode shifted from deep navy (#0F172A) to warmer mid-slate (#1E293B) |
| 2026-03-26 | Warm slates over cold grays | Shifts from Tailwind default gray to slate scale — warmer, more inviting for a collaboration tool |
