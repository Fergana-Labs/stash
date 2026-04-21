# Managed overlay

Proprietary code that does not get mirrored to the public OSS repo lives under a `managed/` subdirectory inside each sub-project:

- `backend/managed/` — FastAPI routes, migrations, and helpers that only run in the hosted deployment.
- `frontend/managed/` — Next.js components and middleware that only run in the hosted deployment.

Anything under a `managed/` subdirectory is private-forever: hosted-only features (Auth0, billing, managed infra) live there and never ship to the community version. Code outside these directories is OSS-eligible by default.

## Why the overlay isn't a single top-level `managed/`

Next.js/Turbopack refuses to resolve imports that walk outside the project root, and Docker builds scope context to the sub-project directory. Keeping each overlay local to its sub-project is the only layout that satisfies both. When the public OSS repo is eventually split off via `git subtree`, the filter needs to exclude `*/managed/` rather than a single directory.

## Currently inside

- `backend/managed/auth0/` — Auth0 JWT validation and `/api/v1/auth0/exchange` endpoint that swaps an Auth0 access token for a stash API key.
- `backend/managed/migrations/` — separate alembic environment (`alembic_version_managed`) holding `m0001_add_auth0_sub.py`.
- `frontend/managed/auth0/` — Next.js-side Auth0 login button and post-login exchange component.

## Running with Auth0

Set these env vars in a managed deploy (in addition to the OSS ones):

```
AUTH0_ENABLED=true
AUTH0_DOMAIN=<tenant>.us.auth0.com
AUTH0_AUDIENCE=<your API identifier>

# Next.js SDK (see https://github.com/auth0/nextjs-auth0)
AUTH0_SECRET=<64-hex random bytes>
AUTH0_CLIENT_ID=<from Auth0 dashboard>
AUTH0_CLIENT_SECRET=<from Auth0 dashboard>
APP_BASE_URL=https://www.joinstash.ai

NEXT_PUBLIC_AUTH0_ENABLED=true
```

`start.sh` runs the managed alembic chain (`backend/managed/alembic.ini`) automatically when `AUTH0_ENABLED=true`.
