# Testing

## Backend

- **Framework:** pytest + pytest-asyncio
- **Database:** Requires a Postgres instance with pgvector (`pgvector/pgvector:pg16`)
- **Config:** `pytest.ini` at the repo root

### Running tests

```bash
# Ensure the test database exists (standalone pgvector container on 5432)
docker start stash-pg 2>/dev/null || docker run -d --name stash-pg -p 5432:5432 \
  -e POSTGRES_USER=stash -e POSTGRES_PASSWORD=stash -e POSTGRES_DB=stash \
  pgvector/pgvector:pg16
psql postgresql://stash:stash@localhost:5432/postgres -c "CREATE DATABASE stash_test"

# Run migrations and tests
DATABASE_URL=postgresql://stash:stash@localhost:5432/stash_test \
  python -m alembic upgrade head

DATABASE_URL=postgresql://stash:stash@localhost:5432/stash_test \
TEST_DATABASE_URL=postgresql://stash:stash@localhost:5432/stash_test \
  python -m pytest backend/tests/ -v
```

### Test suites

| File | Covers |
|------|--------|
| `test_auth.py` | Registration, login, API key auth, password validation |
| `test_permissions.py` | Private-by-default access, owner read/write, share grants, publish records |
| `test_webhooks.py` | SSRF URL validation, secret hashing, delivery logic |
| `test_sleep_agent.py` | Curation tool lifecycle, advisory locks, watermark advancement |
| `test_migrations.py` | Alembic upgrade/history smoke tests |
| `test_collab.py` | Sharing, copy, and collaboration on user-scoped objects |
| `test_websocket.py` | ConnectionManager delivery, dead-socket cleanup, pg_notify, oversized fallback |

### Conventions

- Each test gets a clean database via `TRUNCATE CASCADE` after every test function.
- Use `unique_name()` from `conftest.py` for non-colliding usernames.
- Mock external APIs (Anthropic, OpenAI) — never call real LLM endpoints in tests.

---

## Frontend

- **Framework:** Vitest + @testing-library/react + jsdom
- **Config:** `frontend/vitest.config.ts`

### Running tests

```bash
cd frontend
npm test          # single run
npm run test:watch  # watch mode
```

### Conventions

- Co-locate tests with source files: `{module}.test.ts` or `{module}.test.tsx`
- Use `describe` / `it` blocks
- Use `vi.fn()` / `vi.mock()` for mocking

---

## Plugin tests

- **Framework:** pytest, no database
- **CI:** the `plugin-test` job in `.github/workflows/test.yml` (ubuntu-latest, Python 3.12)

### Running tests

```bash
python -m pytest plugins/tests --no-cov
```

`--no-cov` is required. The root `pytest.ini` sets `addopts = --cov=backend --cov-fail-under=30`,
so a plugin run without it fails on a backend coverage floor it has nothing to do with.

### Hermetic PATH in `test_ensure_cli.py`

`ensure_cli.sh` finds `uv` through `PATH`, so the harness gives the child `PATH` set to its
sandbox directory and **nothing else**. The sandbox is populated from an explicit allowlist —
`bash`, `awk`, `sleep`, `touch` — symlinked in by `_hermetic_bin_dir`. Never widen it with a
host directory "so the script can find tools": that is what made `uv` present-or-absent depend
on the developer's machine, and the assertion meant to prove *no uv → fail loudly* silently
checked the wrong branch while forking a real `uv tool install` on the host.

- A utility the script needs belongs on the allowlist, not on `PATH`. `sleep` is listed even
  though no test asserts on it: without it the uv stub's `sleep 5` becomes "command not found"
  and both "must not block session start" timing tests pass vacuously.
- `sh` and `env` are deliberately absent — stub shebangs name their interpreter by absolute
  path, which the kernel resolves without `PATH`. Every extra allowlisted binary is a leak.
- `find_uv()` also stats `uv` at a few **absolute** paths (`/opt/homebrew/bin/uv`,
  `/usr/local/bin/uv`), which a `PATH` sandbox cannot neutralise. `_run` asserts those are
  absent rather than relaxing the assertion; if that guard fires, the fix belongs in
  `find_uv()`'s candidate list.

---

## Landing page (`www`)

- **Framework:** Vitest for the `www/test/*.test.ts` docs gates; the CSS guard below runs on Node's built-in runner (`node:test`), so it adds no dependency of its own
- **Config:** `vitest.config.ts` scopes Vitest to `test/**/*.test.ts`, which keeps the `node:test` guard out of the Vitest run

### Running tests

```bash
cd www
npm test                                 # the Vitest suites
node --test test/globals-css.test.mjs    # the CSS guard
```

Name the file rather than the directory — Node 26's runner does not accept the bare directory form here.

### What the tests guard

`www/test/globals-css.test.mjs` pins the boundary left by the removal of the `/pages` markdown pastebin (deleted in `ef6027d7`, #1065), whose editor styling survived in the landing page's stylesheet:

| Test | Guards |
|------|--------|
| `editor styling never outlives an editor` | `globals.css` carries no `.tiptap`, `.is-editor-empty`, `.file-page-body` or `.ProseMirror` rules while nothing in `www` imports an editor. It returns early the moment `www` does import one, so it never blocks a real editor. |
| `the prose typography the blog renders survives` | The `.prose` palette, the Tailwind typography plugin import and the `blockquote` rule are still present, and no blog post references a removed editor class. |
| `server-fetched content cannot arrive as raw HTML` | Nothing in `www` renders backend content through `rehype-raw`, so backend HTML cannot reintroduce those class names at runtime. |

`www` has no browser or end-to-end suite. The site's behaviour is covered by `npm run build` plus `npm run lint`; there is no Playwright config and the only frontend E2E tooling in the repo belongs to the product app.
