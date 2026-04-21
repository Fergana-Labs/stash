import { Callout, Code, CodeBlock, H3, P, ParamTable, Title, Subtitle } from "../components";

export default function SelfHostingPage() {
  return (
    <>
      <Title>Self-Hosting</Title>
      <Subtitle>
        Run the full Stash stack on your own infrastructure in under ten minutes.
        One Docker Compose file covers everything.
      </Subtitle>

      <H3>Prerequisites</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { tool: "Docker + Compose", version: "24+" },
          { tool: "Python", version: "3.12+ (CLI only)" },
          { tool: "Node.js", version: "20+ (frontend dev only)" },
        ].map((r) => (
          <div key={r.tool} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-52 flex-shrink-0">{r.tool}</span>
            <span className="text-[13px] text-dim">{r.version}</span>
          </div>
        ))}
      </div>

      <H3>1. Clone and configure</H3>
      <CodeBlock>{`git clone https://github.com/Fergana-Labs/stash.git
cd stash

# Copy the env template and fill in your values
cp .env.example .env`}</CodeBlock>
      <P>
        At minimum set <Code>POSTGRES_USER</Code>, <Code>POSTGRES_PASSWORD</Code>,{" "}
        <Code>PUBLIC_URL</Code> (your domain), and <Code>CORS_ORIGINS</Code>.
        Embeddings default to local sentence-transformers — no API key required.
        Set <Code>OPENAI_API_KEY</Code> or <Code>HF_TOKEN</Code> to use a hosted
        embedding provider instead. The backend itself makes no LLM calls, so
        there are no other keys to configure.
      </P>
      <P>
        Edit <Code>Caddyfile</Code> and replace <Code>app.example.com</Code> with your actual domain.
        Caddy handles TLS automatically via Let&apos;s Encrypt — no certificate management needed.
      </P>

      <H3>2. Start everything</H3>
      <CodeBlock>{`docker compose -f docker-compose.prod.yml up -d`}</CodeBlock>
      <P>This starts four containers:</P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { svc: "postgres", port: "5432", desc: "PostgreSQL 16 with pgvector — stores all workspace data" },
          { svc: "backend", port: "3456", desc: "FastAPI backend" },
          { svc: "frontend", port: "3457", desc: "Next.js UI — dashboard, docs" },
          { svc: "caddy", port: "80/443", desc: "Reverse proxy with automatic HTTPS via Let's Encrypt" },
        ].map((s) => (
          <div key={s.svc} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground font-mono w-24 flex-shrink-0">{s.svc}</span>
            <span className="text-[13px] text-dim w-12 flex-shrink-0">:{s.port}</span>
            <span className="text-[13px] text-dim">{s.desc}</span>
          </div>
        ))}
      </div>
      <P>
        Alembic migrations run automatically on backend startup. Visit{" "}
        <Code>http://localhost:3457</Code> to open the UI.
      </P>

      <H3>Environment variables</H3>
      <ParamTable params={[
        { name: "POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB", type: "string", desc: "Postgres credentials. Defaults are stash/stash/stash — change before going to production.", required: true },
        { name: "DATABASE_URL", type: "string", desc: "Full PostgreSQL connection string. docker-compose.prod.yml auto-builds this from POSTGRES_* — only override if pointing at an external database." },
        { name: "PUBLIC_URL", type: "string", desc: "Frontend origin. Used in invite links and CORS config. Default: http://localhost:3457" },
        { name: "CORS_ORIGINS", type: "string", desc: "Comma-separated allowed origins. Default: http://localhost:3457,http://localhost:3456" },
        { name: "PORT", type: "number", desc: "Backend port. Default: 3456" },
        { name: "DB_POOL_MIN / DB_POOL_MAX", type: "number", desc: "Database connection pool size. Raise DB_POOL_MAX for high-traffic deployments." },
        { name: "EMBEDDING_PROVIDER", type: "string", desc: "openai | huggingface | local | auto. Default: auto (detects from keys; falls back to local sentence-transformers if none set)." },
        { name: "OPENAI_API_KEY", type: "string", desc: "Optional. Enables the OpenAI-compatible embedding provider (also works with any OpenAI-compatible endpoint via EMBEDDING_API_URL)." },
        { name: "HF_TOKEN", type: "string", desc: "Optional. Enables the Hugging Face Inference API embedding provider." },
        { name: "EMBEDDING_MODEL", type: "string", desc: "Override the embedding model name. Defaults depend on provider (text-embedding-3-small, BAAI/bge-small-en-v1.5, all-MiniLM-L6-v2)." },
        { name: "S3_ENDPOINT", type: "string", desc: "S3-compatible endpoint for file uploads (AWS, Cloudflare R2, MinIO). Leave blank to disable." },
        { name: "S3_BUCKET", type: "string", desc: "S3 bucket name." },
        { name: "S3_ACCESS_KEY / S3_SECRET_KEY", type: "string", desc: "S3 credentials." },
      ]} />

      <H3>Optional: file storage</H3>
      <P>
        Stash uses any S3-compatible store for file uploads (images, PDFs, attachments).
        Set <Code>S3_ENDPOINT</Code>, <Code>S3_BUCKET</Code>, <Code>S3_ACCESS_KEY</Code>, and{" "}
        <Code>S3_SECRET_KEY</Code> in your <Code>.env</Code>. MinIO works well for fully
        local deployments:
      </P>
      <CodeBlock>{`# Add to docker-compose.yml services:
minio:
  image: minio/minio
  ports:
    - "9000:9000"
    - "9001:9001"
  environment:
    MINIO_ROOT_USER: stash
    MINIO_ROOT_PASSWORD: stashdev
  command: server /data --console-address ":9001"
  volumes:
    - minio_data:/data`}</CodeBlock>
      <P>Then in <Code>.env</Code>:</P>
      <CodeBlock>{`S3_ENDPOINT=http://localhost:9000
S3_BUCKET=stash
S3_ACCESS_KEY=stash
S3_SECRET_KEY=stashdev
S3_REGION=us-east-1`}</CodeBlock>

      <H3>Production checklist</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { item: "Change default Postgres credentials", detail: "Set POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB in your .env before first run. Docker Compose and DATABASE_URL both pick them up automatically." },
          { item: "Configure CORS_ORIGINS", detail: "Set to your production frontend domain(s) only." },
          { item: "Set PUBLIC_URL", detail: "Set to your production frontend URL so invite links and share links resolve correctly." },
          { item: "Point Caddy at your domain", detail: "Edit Caddyfile: replace app.example.com with your real domain. Caddy auto-provisions Let's Encrypt certificates on first start." },
          { item: "Tune DB_POOL_MAX", detail: "Raise to 50–100 for production load. Ensure your Postgres max_connections is higher." },
          { item: "External Postgres", detail: "For production, use a managed database (RDS, Supabase) with pgvector enabled. Remove the postgres service from docker-compose.prod.yml and set DATABASE_URL directly." },
        ].map((c) => (
          <div key={c.item} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-60 flex-shrink-0">{c.item}</span>
            <p className="text-[14px] text-dim leading-6">{c.detail}</p>
          </div>
        ))}
      </div>

      <H3>Upgrading</H3>
      <CodeBlock>{`git pull
docker compose build
docker compose up -d
# Migrations run automatically on backend startup`}</CodeBlock>

      <H3>Running tests</H3>
      <CodeBlock>{`# Backend — requires a separate test database
docker compose up -d postgres
psql postgresql://stash:stash@localhost:5432/postgres -c "CREATE DATABASE stash_test;"
DATABASE_URL=postgresql://stash:stash@localhost:5432/stash_test \\
  python -m alembic upgrade head
DATABASE_URL=postgresql://stash:stash@localhost:5432/stash_test \\
TEST_DATABASE_URL=postgresql://stash:stash@localhost:5432/stash_test \\
  python -m pytest backend/tests/ -v

# Frontend
cd frontend && npm test`}</CodeBlock>
    </>
  );
}
