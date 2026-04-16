# www — Stash landing page

Standalone Next.js app for stash.ac. Lives alongside `frontend/`, `backend/`, `cli/`, `plugins/`, mirroring how Supabase keeps `apps/www` in its public monorepo.

## Dev

```bash
cd www
npm install
npm run dev    # http://localhost:3100
```

## Stack

- Next.js 16 App Router
- React 19
- Tailwind 4 (`@tailwindcss/postcss`)
- Fonts: Satoshi (Fontshare), Instrument Sans + JetBrains Mono (Google Fonts)

## Design

See `DESIGN.md` in this directory. Inherits from repo-root `/DESIGN.md` (the Stash product design system) with landing-specific extensions.
