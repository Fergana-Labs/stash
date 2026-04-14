import { Callout, Code, CodeBlock, H3, P, ParamTable, Title, Subtitle } from "../components";

export default function SelfHostingPage() {
  return (
    <>
      <Title>Self-Hosting</Title>
      <Subtitle>
        Run the full Octopus stack on your own infrastructure in under ten minutes.
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
      <CodeBlock>{`git clone https://github.com/Fergana-Labs/octopus.git
cd octopus

# Copy the env template and fill in your values
cp .env.example .env`}</CodeBlock>
      <P>
        At minimum set <Code>POSTGRES_USER</Code>, <Code>POSTGRES_PASSWORD</Code>,{" "}
        <Code>OPENAI_API_KEY</Code> (semantic search), and <Code>PUBLIC_URL</Code> (your domain).
      </P>
      <P>
        Edit <Code>Caddyfile</Code> and replace <Code>app.example.com</Code> with your actual domain.
        Caddy handles TLS automatically via Let's Encrypt — no certificate management needed.
      </P>

      <H3>2. Start everything</H3>
      <CodeBlock>{`docker compose -f docker-compose.prod.yml up -d`}</CodeBlock>
      <P>This starts three containers:</P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { svc: "postgres", port: "5432", desc: "PostgreSQL 16 with pgvector — stores all workspace data" },
          { svc: "backend", port: "3456", desc: "FastAPI — REST API" },
          { svc: "frontend", port: "3457", desc: "Next.js UI — dashboard, docs" },
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
        { name: "POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB", type: "string", desc: "Postgres credentials. Defaults are octopus/octopus/octopus — change before going to production." },
        { name: "DATABASE_URL", type: "string", desc: "Full PostgreSQL connection string. Defaults to postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}.", required: true },
        { name: "OPENAI_API_KEY", type: "string", desc: "Required for semantic search (text-embedding-3-small)." },
        { name: "PUBLIC_URL", type: "string", desc: "Frontend origin. Used in invite links and CORS config. Default: http://localhost:3457" },
        { name: "CORS_ORIGINS", type: "string", desc: "Comma-separated allowed origins. Default: http://localhost:3457,http://localhost:3456" },
        { name: "PORT", type: "number", desc: "Backend port. Default: 3456" },
        { name: "DB_POOL_MIN / DB_POOL_MAX", type: "number", desc: "Database connection pool size. Raise DB_POOL_MAX for high-traffic deployments." },
        { name: "S3_ENDPOINT", type: "string", desc: "S3-compatible endpoint for file uploads (AWS, Cloudflare R2, MinIO). Leave blank to disable." },
        { name: "S3_BUCKET", type: "string", desc: "S3 bucket name." },
        { name: "S3_ACCESS_KEY / S3_SECRET_KEY", type: "string", desc: "S3 credentials." },
      ]} />

      <H3>Optional: file storage</H3>
      <P>
        Octopus uses any S3-compatible store for file uploads (images, PDFs, attachments).
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
    MINIO_ROOT_USER: octopus
    MINIO_ROOT_PASSWORD: octopusdev
  command: server /data --console-address ":9001"
  volumes:
    - minio_data:/data`}</CodeBlock>
      <P>Then in <Code>.env</Code>:</P>
      <CodeBlock>{`S3_ENDPOINT=http://localhost:9000
S3_BUCKET=octopus
S3_ACCESS_KEY=octopus
S3_SECRET_KEY=octopusdev
S3_REGION=us-east-1`}</CodeBlock>

      <H3>Production checklist</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { item: "Change default Postgres credentials", detail: "Set POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB in your .env before first run. Docker Compose and DATABASE_URL both pick them up automatically." },
          { item: "Set a strong SECRET_KEY", detail: "Used for signing tokens. Generate with: python -c \"import secrets; print(secrets.token_hex(32))\"" },
          { item: "Configure CORS_ORIGINS", detail: "Set to your production frontend domain(s) only." },
          { item: "Set PUBLIC_URL", detail: "Set to your production frontend URL so invite links and share links resolve correctly." },
          { item: "Enable TLS", detail: "Put Nginx or Caddy in front of both services." },
          { item: "Tune DB_POOL_MAX", detail: "Raise to 50–100 for production load. Ensure your Postgres max_connections is higher." },
          { item: "External Postgres", detail: "For production, use a managed database (RDS, Supabase) with pgvector enabled. Remove the postgres service from docker-compose.yml." },
        ].map((c) => (
          <div key={c.item} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-60 flex-shrink-0">{c.item}</span>
            <p className="text-[14px] text-dim leading-6">{c.detail}</p>
          </div>
        ))}
      </div>

      <Callout type="info">
        The backend exposes an interactive OpenAPI spec at <Code>/docs</Code> (e.g.{" "}
        <Code>http://localhost:3456/docs</Code>). Disable this in production by setting{" "}
        <Code>{"DOCS_ENABLED=false"}</Code> or filtering it in your reverse proxy.
      </Callout>

      <H3>Upgrading</H3>
      <CodeBlock>{`git pull
docker compose build
docker compose up -d
# Migrations run automatically on backend startup`}</CodeBlock>

      <H3>Running tests</H3>
      <CodeBlock>{`# Backend — requires a separate test database
docker compose up -d postgres
psql postgresql://octopus:octopus@localhost:5432/postgres -c "CREATE DATABASE octopus_test;"
DATABASE_URL=postgresql://octopus:octopus@localhost:5432/octopus_test \\
  python -m alembic upgrade head
DATABASE_URL=postgresql://octopus:octopus@localhost:5432/octopus_test \\
TEST_DATABASE_URL=postgresql://octopus:octopus@localhost:5432/octopus_test \\
  python -m pytest backend/tests/ -v

# Frontend
cd frontend && npm test`}</CodeBlock>
    </>
  );
}
