# www — Stash landing page

Standalone Next.js app for joinstash.ai. Lives alongside `frontend/`, `backend/`, `cli/`, `plugins/`, mirroring how Supabase keeps `apps/www` in its public monorepo.

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

See `DESIGN.md` in this directory. Inherits from `/docs/design-system.md` (the Stash product design system) with landing-specific extensions.

## Environment variables

The marketing site runs without any env vars by default. The `/connect-token`
page (CLI sign-in flow for Claude Code-driven setup) needs Auth0:

| Var                          | Purpose                                                |
| ---------------------------- | ------------------------------------------------------ |
| `NEXT_PUBLIC_AUTH0_ENABLED`  | `"true"` to mount Auth0 middleware + enable the page   |
| `NEXT_PUBLIC_API_URL`        | Stash backend (defaults to `https://api.joinstash.ai`) |
| `AUTH0_DOMAIN`               | e.g. `stash-prod.us.auth0.com`                         |
| `AUTH0_AUDIENCE`             | Auth0 API audience validated by the Stash backend      |
| `AUTH0_CLIENT_ID`            | Auth0 application client id                            |
| `AUTH0_CLIENT_SECRET`        | Auth0 application client secret                        |
| `AUTH0_SECRET`               | Cookie-encryption secret (`openssl rand -hex 32`)      |
| `APP_BASE_URL`               | Public URL of this app (`https://joinstash.ai` in prod)    |

When `NEXT_PUBLIC_AUTH0_ENABLED` is unset, `/connect-token` renders a
"sign-in is not configured" message and the auth middleware no-ops.

### Demo form bot protection

Before deploying `/contact-sales`, create a Cloudflare Turnstile widget in Managed
mode with `www.joinstash.ai` as an allowed hostname. Configure these variables on
the **Vercel marketing-site project** (not the Render app):

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Public widget key; required at build time |
| `TURNSTILE_SECRET_KEY` | Server-only widget secret |
| `TURNSTILE_HOSTNAME` | Exact expected hostname, `www.joinstash.ai` in production |
| `POSTMARK_SERVER_TOKEN` | Existing email delivery credential |

Redeploy after setting the variables. The server verifies the token, hostname,
and `contact_sales` action before sending either email. Missing configuration or
failed verification blocks submission. Tokens expire after five minutes and
cannot be reused; the form refreshes verification after each submission attempt.

For local browser checks, use Cloudflare's [official test keys](https://developers.cloudflare.com/turnstile/troubleshooting/testing/)
in local-only environment variables. Never deploy test keys to production. Preview
deployments need a widget and expected hostname configured for their own domain.

Run `npm test` for the submission tests (all external requests are mocked).
This protection does not impose IP or email rate limits; those require a shared
store across the site's serverless instances.
