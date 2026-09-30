# Stash frontend

The Stash product UI: a Next.js (App Router) app that talks to the FastAPI
backend in [`../backend`](../backend). The landing page and public docs are a
separate app in [`../www`](../www).

## Running it

The usual path is `./start.sh` from the repo root, which starts the backend,
workers, and this app together (frontend on port 3457, backend on 3456). See
[Running this repository](../docs/running-stash.md).

To run only the frontend against a backend that is already up:

```bash
npm ci
npm run dev -- -p 3457   # proxies API calls to http://localhost:3456 by default
```

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | Dev server |
| `npm run build` | Production build |
| `npm run lint` | ESLint |
| `npm test` | Vitest unit and component tests |

## Configuration

API requests are proxied to the backend by Next.js rewrites
([`next.config.ts`](next.config.ts)). The build fails if neither backend
variable is set.

| Variable | Purpose |
|---|---|
| `BACKEND_INTERNAL_URL` | Backend origin reachable from the Next.js server (local dev, Docker, self-host) |
| `NEXT_PUBLIC_API_URL` | Backend origin for deployments with a separate public API host |

## Layout

- `src/app/` — routes. Signed-in product pages live under `src/app/(app)/`.
- `src/components/` — shared UI components.
- `src/lib/` — API client and utilities.
- `managed/` — code for the hosted deployment only (Auth0 sign-in). See
  [`docs/managed-overlay.md`](../docs/managed-overlay.md).
