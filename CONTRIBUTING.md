# Contributing to Boozle

Thank you for taking the time to contribute. This guide covers how to set up a
development environment, run the test suite, and submit a pull request.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local development setup](#local-development-setup)
3. [Running tests](#running-tests)
4. [Making changes](#making-changes)
5. [Submitting a pull request](#submitting-a-pull-request)
6. [Code style](#code-style)

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Python | 3.12 |
| Node.js | 20 |
| Docker + Docker Compose | 24 |
| PostgreSQL (pgvector) | 16 (via Docker) |

---

## Local development setup

```bash
# 1. Clone the repository
git clone https://github.com/boozle-ai/boozle.git
cd boozle

# 2. Start Postgres (pgvector)
docker compose up -d postgres

# 3. Backend dependencies (includes test tooling)
pip install -r backend/requirements-dev.txt

# 4. Copy and edit environment variables
cp .env.example .env
# — Set ANTHROPIC_API_KEY and OPENAI_API_KEY if you want sleep-agent / search features
# — SLEEP_AGENT_ENABLED defaults to false; leave it unless you need curation

# 5. Run Alembic migrations
python -m alembic upgrade head

# 6. Frontend dependencies
cd frontend && npm ci && cd ..

# 7. Start everything
./start.sh
#   Backend  → http://localhost:3456
#   Frontend → http://localhost:3457
```

---

## Running tests

Both suites must pass before a PR can be merged.

### Backend

```bash
# Start a test Postgres instance (separate DB from dev)
docker compose up -d postgres

# Create the test database if it doesn't exist
psql postgresql://boozle:boozle@localhost:5432/postgres -c "CREATE DATABASE boozle_test"

# Run migrations against the test DB
# Note: Alembic reads DATABASE_URL, not TEST_DATABASE_URL
DATABASE_URL=postgresql://boozle:boozle@localhost:5432/boozle_test \
  python -m alembic upgrade head

# Run pytest (set both vars so config.py and conftest.py agree)
DATABASE_URL=postgresql://boozle:boozle@localhost:5432/boozle_test \
TEST_DATABASE_URL=postgresql://boozle:boozle@localhost:5432/boozle_test \
  python -m pytest backend/tests/ -v
```

### Frontend

```bash
cd frontend
npm test
```

---

## Making changes

- Keep PRs focused. One logical change per pull request is strongly preferred.
- Add or update tests for any behaviour you change.
- Run both test suites locally before pushing.
- Follow the naming conventions in `ARCHITECTURE.md`: use **Boozle** everywhere.
  The name `moltchat` is deprecated — do not introduce it in new code, comments, or docs.

### Adding a schema change

1. Create a new Alembic migration:
   ```bash
   python -m alembic revision -m "add_my_column"
   ```
2. Edit the generated file in `backend/migrations/versions/` — write both
   `upgrade()` and `downgrade()` using raw SQL via `op.execute()`.
3. Run `python -m alembic upgrade head` to verify.
4. Add a corresponding test in `backend/tests/test_migrations.py` if the
   migration has non-trivial data logic.

---

## Submitting a pull request

1. Fork the repository and create a feature branch off `main`.
2. Ensure both test suites pass locally.
3. Open a PR against `main`. The CI pipeline runs both suites automatically.
4. Describe the motivation for the change in the PR body. Link any related issues.
5. A maintainer will review and merge once CI is green.

---

## Code style

- **Python:** PEP 8, type annotations on all public functions. No `mypy` enforcement yet, but annotations help reviewers.
- **TypeScript/React:** ESLint with `eslint-config-next`. Run `npm run lint` before pushing.
- **SQL:** All queries must use parameterised placeholders (`$1`, `$2`, ...). No string interpolation in SQL.
- **Comments:** Explain *why*, not *what*. Avoid narrating code with comments like `# increment counter`.
