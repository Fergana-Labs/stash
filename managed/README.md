# managed/

This directory holds **proprietary code** that does not get mirrored to the public OSS repo. Anything placed here is private-forever: hosted-only features (Auth0, billing, managed infra) live here and never ship to the community version.

When in doubt, put code **outside** this directory — the default is OSS-eligible. Only reach for `managed/` when the code is intentionally private.

## Why this directory exists

Stash will eventually live in two repos:

- **Public OSS repo** — community-facing source of truth.
- **Private managed repo** (this repo) — OSS code + managed-only additions.

When the public repo is created, everything outside `managed/` will be mirrored to it via `git subtree`. Everything inside `managed/` stays here.

Keeping the boundary clean now means the eventual open-sourcing step is mechanical instead of a big refactor.

## Currently inside

- `backend/auth0/` — Auth0 JWT validation + `/api/v1/auth0/exchange` endpoint that swaps an Auth0 access token for an octopus api_key.
- `backend/migrations/` — separate alembic environment (`alembic_version_managed`) holding `m0001_add_auth0_sub.py`.
- `frontend/auth0/` — Next.js-side Auth0 login button and post-login exchange component.

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
APP_BASE_URL=https://www.stash.ac
AUTH0_DOMAIN=<tenant>.us.auth0.com

NEXT_PUBLIC_AUTH0_ENABLED=true
```

`start.sh` runs the managed alembic chain automatically when `AUTH0_ENABLED=true`.

