import { Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

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
cp .env.example .env
# Set PUBLIC_URL and CORS_ORIGINS in .env, then replace app.example.com in Caddyfile.
docker compose -f docker-compose.prod.yml up -d
curl https://app.example.com/health   # wait for {"status":"ok"}`}</CodeBlock>
      <P>
        Then install the CLI and connect a repo:
      </P>
      <CodeBlock>{`pip install stashai   # or: uv tool install stashai
cd /path/to/your/repo
stash config base_url https://app.example.com
stash login`}</CodeBlock>
      <P>
        The UI is at your <Code>PUBLIC_URL</Code>.{" "}
        <Code>stash login</Code> opens it to register and authorize the CLI.
      </P>

      <H3>Upgrading</H3>
      <CodeBlock>{`git pull
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d`}</CodeBlock>
    </>
  );
}
