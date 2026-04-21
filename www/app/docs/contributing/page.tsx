import { Callout, Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function ContributingPage() {
  return (
    <>
      <Title>Contributing</Title>
      <Subtitle>
        How to set up a local development environment, run the test suites, and
        submit a pull request to Stash.
      </Subtitle>

      <H3>Prerequisites</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { tool: "Python", version: "3.12+" },
          { tool: "Node.js", version: "20+" },
          { tool: "Docker + Docker Compose", version: "24+" },
          { tool: "PostgreSQL with pgvector", version: "16 (via Docker)" },
        ].map((r) => (
          <div key={r.tool} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-52 flex-shrink-0">{r.tool}</span>
            <span className="text-[13px] text-dim">{r.version}</span>
          </div>
        ))}
      </div>

      <H3>Local development setup</H3>
      <CodeBlock>{`# 1. Clone
git clone https://github.com/Fergana-Labs/stash.git
cd stash

# 2. Start Postgres
docker compose up -d postgres

# 3. Backend dependencies (includes test tooling)
pip install -r backend/requirements-dev.txt

# 4. Configure environment
cp .env.example .env
# Embeddings default to local sentence-transformers — no key needed.
# Set OPENAI_API_KEY or HF_TOKEN to use a hosted embedding provider instead.

# 5. Apply database migrations
python -m alembic upgrade head

# 6. Frontend dependencies
cd frontend && npm ci && cd ..

# 7. Start both services
./start.sh
#   Backend  → http://localhost:3456
#   Frontend → http://localhost:3457`}</CodeBlock>

      <H3>Running tests</H3>
      <P>Both suites must pass before a PR can be merged.</P>
      <CodeBlock>{`# Backend — create a separate test database
psql postgresql://stash:stash@localhost:5432/postgres -c "CREATE DATABASE stash_test;"

# Run migrations against the test DB
DATABASE_URL=postgresql://stash:stash@localhost:5432/stash_test \\
  python -m alembic upgrade head

# Run the full test suite
DATABASE_URL=postgresql://stash:stash@localhost:5432/stash_test \\
TEST_DATABASE_URL=postgresql://stash:stash@localhost:5432/stash_test \\
  python -m pytest backend/tests/ -v

# Frontend
cd frontend && npm test`}</CodeBlock>

      <H3>Making changes</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { rule: "One change per PR", detail: "Keep pull requests focused on a single logical change." },
          { rule: "Tests required", detail: "Add or update tests for any behaviour you change. The minimum coverage threshold is enforced by CI." },
          { rule: "Schema changes", detail: "Create an Alembic migration (python -m alembic revision -m \"description\"). Write both upgrade() and downgrade() using op.execute() with raw SQL." },
          { rule: "SQL safety", detail: "All queries must use parameterised placeholders ($1, $2, …). No string interpolation in SQL." },
          { rule: "Python style", detail: "PEP 8, type annotations on all public functions." },
          { rule: "TypeScript style", detail: "ESLint with eslint-config-next. Run npm run lint before pushing." },
          { rule: "Comments", detail: "Explain why, not what. Avoid narrating obvious code." },
        ].map((r) => (
          <div key={r.rule} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-44 flex-shrink-0">{r.rule}</span>
            <p className="text-[14px] text-dim leading-6">{r.detail}</p>
          </div>
        ))}
      </div>

      <H3>Submitting a pull request</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          "Fork the repository and create a feature branch off main.",
          "Ensure both test suites pass locally.",
          "Open a PR against main. The CI pipeline runs both suites automatically.",
          "Describe the motivation for the change in the PR body. Link any related issues.",
          "A maintainer will review and merge once CI is green.",
        ].map((step, i) => (
          <div key={i} className="flex gap-5 px-5 py-4">
            <span className="text-[11px] font-mono text-muted pt-0.5 flex-shrink-0">0{i + 1}</span>
            <p className="text-[14px] text-dim leading-6">{step}</p>
          </div>
        ))}
      </div>

      <H3>Adding a schema change</H3>
      <CodeBlock>{`# 1. Create a new migration
python -m alembic revision -m "add_my_column"

# 2. Edit backend/migrations/versions/<hash>_add_my_column.py
#    Write both upgrade() and downgrade() using op.execute() with raw SQL.

# 3. Apply and verify locally
python -m alembic upgrade head

# 4. Add a migration test if there is non-trivial data logic
#    → backend/tests/test_migrations.py`}</CodeBlock>

      <Callout type="info">
        Questions? Open a GitHub Discussion or drop a message in the workspace chat. We
        review PRs on a best-effort basis and aim to respond within 48 hours on weekdays.
      </Callout>
    </>
  );
}
