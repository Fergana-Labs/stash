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
          { tool: "Git", version: "any" },
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
cp .env.example .env`}</CodeBlock>
      <P>
        The defaults in <Code>.env.example</Code> work out of the box for local
        use. For a production deployment, change <Code>POSTGRES_PASSWORD</Code>,
        set <Code>PUBLIC_URL</Code> to your domain, and update{" "}
        <Code>CORS_ORIGINS</Code> to match.
      </P>

      <H3>2. Start everything</H3>
      <P>
        <strong>Local (no domain, no TLS):</strong>
      </P>
      <CodeBlock>{`docker compose up -d --build
curl http://localhost:3456/health`}</CodeBlock>
      <P>
        The UI runs at <Code>http://localhost:3457</Code> and the API at{" "}
        <Code>http://localhost:3456</Code>. Continue once the health check
        prints <Code>{`{"status":"ok"}`}</Code>.
      </P>
      <P>
        <strong>Production (custom domain with automatic TLS):</strong>
      </P>
      <CodeBlock>{`# Edit Caddyfile — replace app.example.com with your domain
docker compose -f docker-compose.prod.yml up -d --build`}</CodeBlock>
      <P>
        Caddy handles TLS automatically via Let&apos;s Encrypt. The production
        compose adds Caddy as a reverse proxy and keeps internal ports off the
        host.
      </P>
      <P>This starts eight services:</P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { svc: "postgres", desc: "PostgreSQL 16 with pgvector" },
          { svc: "redis", desc: "Task queue and caching" },
          { svc: "backend", desc: "FastAPI API server (runs Alembic migrations on startup)" },
          { svc: "worker", desc: "Celery worker for background tasks" },
          { svc: "beat", desc: "Celery beat scheduler" },
          { svc: "frontend", desc: "Next.js UI" },
          { svc: "collab", desc: "Yjs collaboration server for live editing" },
          { svc: "caddy", desc: "Reverse proxy with automatic HTTPS (production only)" },
        ].map((s) => (
          <div key={s.svc} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground font-mono w-24 flex-shrink-0">{s.svc}</span>
            <span className="text-[13px] text-dim">{s.desc}</span>
          </div>
        ))}
      </div>

      <H3>3. Install the CLI</H3>
      <P>
        The CLI connects your repos to your self-hosted instance. Install it
        and point it at your local API:
      </P>
      <CodeBlock>{`# With pip
pip install stashai

# Or with uv (no Python install required)
uv tool install stashai`}</CodeBlock>
      <P>
        Then from any repo you want to connect:
      </P>
      <CodeBlock>{`cd /path/to/your/repo
stash config base_url http://localhost:3456
stash login`}</CodeBlock>
      <P>
        <Code>stash login</Code> opens the local UI to register or sign in,
        then walks through agent and repo setup.{" "}
        <Code>base_url</Code> tells the CLI to use your local server instead
        of the hosted version — skip this step only if you set a custom{" "}
        <Code>PUBLIC_URL</Code> in your <Code>.env</Code> and want to use
        that instead.
      </P>

      <H3>Environment variables</H3>
      <P>
        See <Code>.env.example</Code> for the full list with inline
        documentation. Key variables:
      </P>
      <ParamTable params={[
        { name: "POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB", type: "string", desc: "Postgres credentials. Defaults are stash/stash/stash — change before going to production.", required: true },
        { name: "DATABASE_URL", type: "string", desc: "Full PostgreSQL connection string. Docker Compose auto-builds this from POSTGRES_* — only override if pointing at an external database." },
        { name: "PUBLIC_URL", type: "string", desc: "Frontend origin. Used in invite links, share links, and CORS config. Default: http://localhost:3457" },
        { name: "CORS_ORIGINS", type: "string", desc: "Comma-separated allowed origins. Default: http://localhost:3457,http://localhost:3456" },
        { name: "ANTHROPIC_API_KEY", type: "string", desc: "Optional. Enables ask-the-workspace chat and automatic session summarization. Without it those features are quietly disabled — core functionality (sessions, pages, files, search) works fine." },
        { name: "ANTHROPIC_MODEL", type: "string", desc: "Quality-tier model for ask-the-workspace. Default: claude-sonnet-4-6" },
        { name: "ANTHROPIC_FAST_MODEL", type: "string", desc: "Fast-tier model for session titles. Default: claude-haiku-4-5" },
        { name: "EMBEDDING_PROVIDER", type: "string", desc: "openai | huggingface | local | auto. Default: auto (detects from keys; falls back to local sentence-transformers if none set)." },
        { name: "OPENAI_API_KEY", type: "string", desc: "Optional. Enables the OpenAI-compatible embedding provider (also works with any OpenAI-compatible endpoint via EMBEDDING_API_URL)." },
        { name: "HF_TOKEN", type: "string", desc: "Optional. Enables the Hugging Face Inference API embedding provider." },
        { name: "EMBEDDING_MODEL", type: "string", desc: "Override the embedding model name. Defaults depend on provider (text-embedding-3-small, BAAI/bge-small-en-v1.5, all-MiniLM-L6-v2)." },
        { name: "S3_ENDPOINT", type: "string", desc: "S3-compatible endpoint for file uploads (AWS, Cloudflare R2, MinIO). Leave blank to disable." },
        { name: "S3_BUCKET / S3_ACCESS_KEY / S3_SECRET_KEY", type: "string", desc: "S3 bucket name and credentials." },
        { name: "INTEGRATIONS_ENCRYPTION_KEY", type: "string", desc: "Fernet key for encrypting OAuth tokens (GitHub, Google Drive, Notion). Generate once, never rotate. Leave blank to disable integrations." },
        { name: "LINEAR_API_KEY", type: "string", desc: "Optional. Enables Linear ticket enrichment for sessions that reference issue identifiers." },
        { name: "COLLAB_PUBLIC_URL", type: "string", desc: "WebSocket URL for the collab server if not routed under /collab. Only needed for non-standard proxy setups." },
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
          { item: "Change default Postgres credentials", detail: "Set POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB in your .env before first run." },
          { item: "Configure CORS_ORIGINS", detail: "Set to your production frontend domain(s) only." },
          { item: "Set PUBLIC_URL", detail: "Set to your production frontend URL so invite links and share links resolve correctly." },
          { item: "Point Caddy at your domain", detail: "Edit Caddyfile: replace app.example.com with your real domain. Caddy auto-provisions Let's Encrypt certificates on first start." },
          { item: "Generate INTEGRATIONS_ENCRYPTION_KEY", detail: "Required for GitHub/Google/Notion OAuth. Generate a Fernet key once and never rotate it — see .env.example for the command." },
          { item: "External Postgres", detail: "For production, consider a managed database (RDS, Supabase) with pgvector enabled. Remove the postgres service from docker-compose.prod.yml and set DATABASE_URL directly." },
        ].map((c) => (
          <div key={c.item} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-60 flex-shrink-0">{c.item}</span>
            <p className="text-[14px] text-dim leading-6">{c.detail}</p>
          </div>
        ))}
      </div>

      <Callout type="info">
        The backend exposes an interactive OpenAPI spec at <Code>/docs</Code> (e.g.{" "}
        <Code>http://localhost:3456/docs</Code>). For production, block the path at your
        reverse proxy (Caddy) rather than exposing the schema publicly.
      </Callout>

      <H3>Upgrading</H3>
      <CodeBlock>{`git pull
docker compose up -d --build
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
