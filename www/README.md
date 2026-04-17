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

## Environment variables

The marketing site runs without any env vars by default. The `/connect-token`
page (CLI sign-in handoff for Claude Code-driven setup) needs Auth0:

| Var                          | Purpose                                                |
| ---------------------------- | ------------------------------------------------------ |
| `NEXT_PUBLIC_AUTH0_ENABLED`  | `"true"` to mount Auth0 middleware + enable the page   |
| `NEXT_PUBLIC_API_URL`        | Stash backend (defaults to `https://api.stash.ac`) |
| `AUTH0_DOMAIN`               | e.g. `stash-prod.us.auth0.com`                         |
| `AUTH0_CLIENT_ID`            | Auth0 application client id                            |
| `AUTH0_CLIENT_SECRET`        | Auth0 application client secret                        |
| `AUTH0_SECRET`               | Cookie-encryption secret (`openssl rand -hex 32`)      |
| `APP_BASE_URL`               | Public URL of this app (`https://stash.ac` in prod)    |

When `NEXT_PUBLIC_AUTH0_ENABLED` is unset, `/connect-token` renders a
"sign-in is not configured" message and the auth middleware no-ops.
