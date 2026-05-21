import { Callout, Code, CodeBlock, H3, P, ParamTable, Title, Subtitle } from "../components";

export default function SelfHostingPage() {
  return (
    <>
      <Title>Self-Hosting</Title>
      <Subtitle>
        Run Stash on your own machine with Docker Compose.
      </Subtitle>

      <H3>Quick start</H3>
      <CodeBlock>{`git clone https://github.com/Fergana-Labs/stash.git
cd stash
docker compose up -d --build
curl http://localhost:3456/health   # wait for {"status":"ok"}`}</CodeBlock>
      <P>
        Then install the CLI and connect a repo:
      </P>
      <CodeBlock>{`pip install stashai   # or: uv tool install stashai
cd /path/to/your/repo
stash config base_url http://localhost:3456
stash login`}</CodeBlock>
      <P>
        The UI is at <Code>http://localhost:3457</Code>.{" "}
        <Code>stash login</Code> opens it to register and authorize the CLI.
      </P>

      <H3>Production deployment</H3>
      <P>
        For a real domain with automatic TLS, use the production compose file:
      </P>
      <CodeBlock>{`cp .env.example .env              # set POSTGRES_PASSWORD, PUBLIC_URL, CORS_ORIGINS
# Edit Caddyfile — replace app.example.com with your domain
docker compose -f docker-compose.prod.yml up -d --build`}</CodeBlock>

      <H3>Environment variables</H3>
      <P>
        See <Code>.env.example</Code> for the full list. Key variables:
      </P>
      <ParamTable params={[
        { name: "POSTGRES_PASSWORD", type: "string", desc: "Change from the default before going to production.", required: true },
        { name: "PUBLIC_URL", type: "string", desc: "Frontend origin for invite/share links and CORS. Default: http://localhost:3457" },
        { name: "CORS_ORIGINS", type: "string", desc: "Comma-separated allowed origins. Default: http://localhost:3457,http://localhost:3456" },
        { name: "ANTHROPIC_API_KEY", type: "string", desc: "Optional. Enables ask-the-workspace and session summarization. Core features work without it." },
        { name: "EMBEDDING_PROVIDER", type: "string", desc: "openai | huggingface | local | auto (default). Falls back to local sentence-transformers when no API keys are set." },
        { name: "S3_ENDPOINT / S3_BUCKET / S3_ACCESS_KEY / S3_SECRET_KEY", type: "string", desc: "S3-compatible store for file uploads. Leave blank to disable." },
      ]} />

      <H3>Upgrading</H3>
      <CodeBlock>{`git pull
docker compose up -d --build`}</CodeBlock>

      <Callout type="info">
        Alembic migrations run automatically on backend startup — no manual
        steps needed after upgrading.
      </Callout>
    </>
  );
}
