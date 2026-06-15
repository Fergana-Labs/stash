import { Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function SelfHostingPage() {
  return (
    <>
      <Title>Self-Hosting</Title>
      <Subtitle>
        Run Stash on your own machine with Docker Compose and prebuilt GHCR images.
      </Subtitle>
      <P>
        The production Compose file pulls Stash application images from{" "}
        <Code>ghcr.io/fergana-labs</Code>. You do not need to build the backend,
        frontend, or collab containers locally.
      </P>

      <H3>Host locally</H3>
      <CodeBlock>{`git clone https://github.com/Fergana-Labs/stash.git
cd stash
cp .env.example .env
docker compose -f docker-compose.prod.yml -f docker-compose.local.yml pull
docker compose -f docker-compose.prod.yml -f docker-compose.local.yml up -d
curl http://localhost:3456/health   # wait for {"status":"ok"}`}</CodeBlock>
      <P>
        This local setup exposes the app directly on localhost and disables
        Caddy, so you do not need ports 80/443 or a public domain.
      </P>

      <H3>Production domain</H3>
      <CodeBlock>{`cp .env.example .env
# Set PUBLIC_URL and CORS_ORIGINS in .env, then replace app.example.com in Caddyfile.
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
curl https://app.example.com/health   # wait for {"status":"ok"}`}</CodeBlock>
      <P>
        Then install the CLI and connect a repo:
      </P>
      <CodeBlock>{`pip install stashai   # or: uv tool install stashai
cd /path/to/your/repo
stash signin   # choose "Self-host" and enter http://localhost:3456`}</CodeBlock>
      <P>
        Enter your public URL instead of <Code>http://localhost:3456</Code> for a
        Caddy-backed install. <Code>stash signin</Code> opens it to register and
        authorize the CLI; change the endpoint later from <Code>stash settings</Code>.
      </P>

      <H3>Upgrading</H3>
      <CodeBlock>{`git pull
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d`}</CodeBlock>
    </>
  );
}
