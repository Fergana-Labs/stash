# Changelog

All notable changes to Octopus are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- MIT License for open-source distribution.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` for community governance.
- Alembic migration system replacing ad-hoc schema management.
- Rate limiting on `/register` (5/min) and `/login` (10/min) via slowapi.
- SSRF protection on webhook URLs (blocks private/internal networks).
- HMAC-SHA256 webhook payload signing with `X-Webhook-Signature` header.
- Persistent webhook delivery queue (`webhook_deliveries` table) with exponential backoff.
- Postgres `LISTEN/NOTIFY` for cross-process WebSocket/SSE broadcast.
- Postgres advisory locks for distributed singleton patterns (sleep agent, webhook delivery).
- Bounded LRU cache for `last_seen` debouncing to prevent memory leaks.
- `pytest-cov` integration with 30% coverage floor enforced in CI.
- Test suites: workspace CRUD, chat messaging, WebSocket/ConnectionManager, migrations.
- Non-root user in backend Dockerfile.
- `__init__.py` files across all backend packages.

### Fixed
- Permission service: non-admin members could gain write access to "inherit" objects without explicit share.
- Permission service: redundant DB queries for role/visibility fetching.
- Webhook double-serialization of JSONB payload.
- Webhook delivery race condition across multiple workers (advisory lock).
- `pg_notify` callback used `run_coroutine_threadsafe` from the event loop thread (now uses `create_task`).
- `remove_listener` on shutdown created a new callback instead of reusing the registered one.
- `httpx.AsyncClient` churn — now reused per delivery batch.
- Test isolation: per-test `TRUNCATE CASCADE` on all application tables.

### Changed
- Product renamed from `moltchat` to **Octopus**; default DB credentials updated.
- Frontend package name changed to `octopus`.
- Plugin default endpoints updated to `https://getboozle.com`.
- `TESTING.md` rewritten to reflect actual backend + frontend test setup.
- Configuration centralized in `backend/config.py` with full `.env.example` documentation.
